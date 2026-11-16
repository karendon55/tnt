"""
Auto-categorización local, 100% sin LLM.

Estrategia:
- Fuente A (bootstrap): los extractos de ING ya traen categoría → source_hint.
  Mapeamos a la jerarquía de la BD y, en paralelo, extraemos tokens de la
  descripción para generar reglas aprendidas ("MERCADONA" → Alimentación).
- Fuente B: el usuario puede recategorizar cualquier movimiento. Eso refuerza
  reglas y reentrena.
- Aplicación: para cada tx sin categoría, busca las reglas que casan con su
  descripción por palabra entera y se queda con la que gana. Las dos cosas las
  decide rule_matching.py, el único sitio que lo hace.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

from app.services.categories import resolve_category
from app.services.rule_matching import matching_rules, pattern_matches, rule_rank

# Palabras a ignorar al extraer tokens distintivos
_STOPWORDS = {
    "PAGO", "RECIBO", "COMPRA", "DEVOLUCION", "TRANSF", "TRANSFERENCIA",
    "EN", "DE", "DEL", "LA", "EL", "LOS", "LAS", "POR", "PARA", "CON",
    "SL", "SA", "SLU", "SAU", "ES", "ESPA", "MADRID", "BARCELONA",
    "BIZUM", "ENVIADO", "RECIBIDO", "FECHA", "OPERACION", "RECIBOS",
    "VARIOS", "NOMINA",
    "CON-", "C.C.", "CC",
}

_TOKEN_RE = re.compile(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9]{2,}")


def extract_tokens(description: str) -> list[str]:
    """Extrae palabras significativas en MAYÚSCULAS de una descripción."""
    up = description.upper()
    tokens = _TOKEN_RE.findall(up)
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 4]


# ====== Aprendizaje de reglas ======

MIN_CONFIDENCE = 0.70

# Huella (hash) de lo cargado del histórico de HomeBank: «homebank:<año>:…».
# No enseña reglas ni quita las que hay: sus categorías salen de una tabla de
# equivalencias, no de cómo categoriza el usuario hoy, y con ellas TNT dejaría
# de categorizar como antes de cargarlo. Decidido por el usuario.
PREFIJO_HISTORICO = "homebank:"


def learn_rules_from_known(cur: sqlite3.Cursor) -> int:
    """
    Recorre las transacciones que ya tienen category_id y actualiza
    category_rules con los tokens dominantes de cada descripción.
    Regla de confianza: un token genera regla si al menos el 70% de las
    transacciones donde aparece pertenecen a la misma categoría.

    También *revoca* las reglas aprendidas que la evidencia actual ya no
    respalda: si el usuario recategoriza a mano, el token deja de ser
    dominante y su regla debe desaparecer. Sin esto, una regla aprendida
    con datos antiguos sobrevive para siempre y sigue clasificando mal
    (p. ej. "REPSOL"→Luz y gas aprendido de los recibos domiciliados,
    aplicándose luego a "REPSOL WAYLET", que es combustible).

    Lo cargado del histórico (`PREFIJO_HISTORICO`) no cuenta, ni para crear
    ni para revocar. Las reglas 'manual' y 'builtin' nunca se tocan aquí.
    Devuelve el número de reglas creadas.
    """
    rows = cur.execute(
        "SELECT description, category_id FROM transactions "
        "WHERE category_id IS NOT NULL AND hash NOT LIKE ?", (PREFIJO_HISTORICO + "%",)
    ).fetchall()

    token_cat_counts: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for tok in extract_tokens(r["description"]):
            token_cat_counts[tok][r["category_id"]] += 1

    created = 0
    for tok, counter in token_cat_counts.items():
        total = sum(counter.values())
        if total < 1:
            continue
        cat_id, cat_hits = counter.most_common(1)[0]
        if cat_hits / total < MIN_CONFIDENCE:
            continue
        # Con una sola aparición exigimos un token distintivo: alfabético y
        # largo. Los códigos de referencia del banco ("NI2394WW4",
        # "ETAMOB00001232707") llevan dígitos y solo generan ruido.
        if total == 1 and (len(tok) < 5 or any(c.isdigit() for c in tok)):
            continue

        existing = cur.execute(
            "SELECT id, hits FROM category_rules WHERE pattern = ? AND category_id = ?",
            (tok, cat_id),
        ).fetchone()
        if existing:
            cur.execute(
                "UPDATE category_rules SET hits = ? WHERE id = ?",
                (cat_hits, existing["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO category_rules(pattern, category_id, source, hits) "
                "VALUES (?, ?, 'learned', ?)",
                (tok, cat_id, cat_hits),
            )
            created += 1

    _revoke_unsupported_learned_rules(cur, token_cat_counts)
    return created


def _revoke_unsupported_learned_rules(
    cur: sqlite3.Cursor, token_cat_counts: dict[str, Counter]
) -> int:
    """Borra las reglas 'learned' que la evidencia actual ya no sostiene.

    Una regla deja de sostenerse cuando menos del 70% de las transacciones
    que contienen su token pertenecen a la categoría que la regla asigna.
    Devuelve cuántas se borraron.
    """
    stale: list[int] = []
    for rule in cur.execute(
        "SELECT id, pattern, category_id FROM category_rules WHERE source = 'learned'"
    ).fetchall():
        counter = token_cat_counts.get(rule["pattern"])
        if not counter:
            # El token ya no aparece en ninguna transacción categorizada.
            stale.append(rule["id"])
            continue
        total = sum(counter.values())
        support = counter.get(rule["category_id"], 0) / total
        if support < MIN_CONFIDENCE:
            stale.append(rule["id"])

    for rule_id in stale:
        cur.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
    return len(stale)


# ====== Aplicación de reglas a transacciones sin categoría ======

def apply_rules_to_uncategorized(
    cur: sqlite3.Cursor, batch_id: int | None = None
) -> tuple[int, int]:
    """
    Para cada transacción con category_id NULL, busca las reglas que casan con
    su descripción y se queda con la que gana (ver `rule_matching`).

    Recorre TODA la base, no solo lo que acaba de entrar: una regla nueva
    también rescata movimientos viejos que estaban sin categoría, y eso es
    justo lo que se quiere. Pero entonces el total no se puede enseñar como
    «lo que ha categorizado esta importación», así que se devuelve partido:

        (categorizadas en total, categorizadas que venían en `batch_id`)

    Sin `batch_id`, la segunda cifra es 0.
    """
    rules = cur.execute(
        "SELECT pattern, category_id, priority, hits, source FROM category_rules"
    ).fetchall()
    if not rules:
        return 0, 0

    uncat = cur.execute(
        "SELECT id, description, import_batch_id FROM transactions WHERE category_id IS NULL"
    ).fetchall()

    updated = 0
    updated_batch = 0
    for tx in uncat:
        matching = matching_rules(rules, tx["description"])
        if not matching:
            continue
        best = max(matching, key=rule_rank)

        # Confianza: qué parte de la evidencia coincidente apoya la categoría
        # elegida (no solo los hits del ganador).
        total_hits = sum(max(r["hits"], 1) for r in matching)
        agree_hits = sum(
            max(r["hits"], 1) for r in matching
            if r["category_id"] == best["category_id"]
        )
        conf = min(1.0, agree_hits / max(total_hits, 1))

        cur.execute(
            "UPDATE transactions SET category_id = ?, auto_categorized = 1, "
            "confidence = ? WHERE id = ?",
            (best["category_id"], round(conf, 3), tx["id"]),
        )
        updated += 1
        if batch_id is not None and tx["import_batch_id"] == batch_id:
            updated_batch += 1
    return updated, updated_batch


def apply_rule_retroactively(cur: sqlite3.Cursor, pattern: str, category_id: int) -> int:
    """Pone `category_id` a los movimientos sin categoría con los que casa
    `pattern`: lo que hace una regla recién creada. No mira las demás reglas
    ni toca nada que ya tenga categoría. Devuelve cuántos ha categorizado."""
    ids = [tx["id"] for tx in cur.execute(
        "SELECT id, description FROM transactions WHERE category_id IS NULL"
    ).fetchall() if pattern_matches(pattern, tx["description"].upper())]
    cur.executemany(
        "UPDATE transactions SET category_id = ?, auto_categorized = 1, "
        "confidence = 0.9 WHERE id = ?",
        [(category_id, tx_id) for tx_id in ids],
    )
    return len(ids)


def retrain_and_apply(
    cur: sqlite3.Cursor, batch_id: int | None = None
) -> tuple[int, int, int]:
    """Reaprende reglas y las aplica.

    Devuelve (reglas creadas, categorizadas en total, categorizadas del lote).
    La tercera cifra existe para que la pantalla de importación pueda decir
    cuántas son de lo que acabas de subir y cuántas son movimientos antiguos
    rescatados de paso: mezclarlas hacía que un fichero de 3 filas presumiera
    de haber categorizado 71.
    """
    seed_builtin_rules(cur)
    created = learn_rules_from_known(cur)
    applied, applied_batch = apply_rules_to_uncategorized(cur, batch_id=batch_id)
    return created, applied, applied_batch


# ====== Reglas integradas para patrones bancarios comunes en España ======

_BUILTIN: list[tuple[str, str, int]] = [
    # (patrón, categoría hint, prioridad)
    # Bizum: el patrón genérico apunta a «Otros gastos › Transferencias», que
    # es categoría de GASTO. Un "BIZUM RECIBIDO" es dinero que entra, así que
    # necesita su propia regla o acaba restando en vez de sumar.
    # Transferencias y traspasos van al árbol de ING, el que traen sus
    # importaciones: la «Transferencias» propia de TNT se unificó con él (ver
    # unificar_transferencias.py). Apuntar aquí a otra la volvería a crear.
    ("BIZUM ENVIADO",  "Otros gastos|Bizum enviado",         160),
    ("BIZUM RECIBIDO", "Ingresos varios|Bizum recibido",     160),
    ("BIZUM",          "Otros gastos|Transferencias",        150),
    ("NOMINA",         "Nómina y otras prestaciones|Nómina o Pensión", 200),
    ("PREST. DESEMPLEO", "Nómina y otras prestaciones|Desempleo",      200),
    ("DESEMPLEO",      "Nómina y otras prestaciones|Desempleo",       180),
    ("REINT.CAJERO",   "Sin categoría",                      140),
    ("REINTEGRO",      "Sin categoría",                      140),
    ("COMISIONES",     "Impuestos y comisiones|Comisiones bancarias", 180),
    ("COMISION",       "Impuestos y comisiones|Comisiones bancarias", 170),
    ("TRASPASO",       "Movimientos excluidos|Traspaso entre cuentas", 150),
    ("TRASPASOS",      "Movimientos excluidos|Traspaso entre cuentas", 150),
    ("MERCADONA",      "Alimentación|Supermercados y alimentación",   150),
    ("LIDL",           "Alimentación|Supermercados y alimentación",   150),
    ("ALCAMPO",        "Alimentación|Supermercados y alimentación",   150),
    ("CARREFOUR",      "Alimentación|Supermercados y alimentación",   150),
    # Repsol vende carburante y también es comercializadora de luz/gas. El
    # patrón compuesto desambigua: gana al genérico "REPSOL" por ser más
    # específico (ver rule_matching.rule_rank).
    ("REPSOL WAYLET",  "Transporte|Combustible",             160),
    ("RECIBO REPSOL",  "Hogar|Luz y gas",                    160),
    ("REPSOL",         "Transporte|Combustible",             150),
    ("CEPSA",          "Transporte|Combustible",             150),
    ("WAYLET",         "Transporte|Combustible",             150),
    ("IBERDROLA",      "Hogar|Luz y gas",                    150),
    ("ENDESA",         "Hogar|Luz y gas",                    150),
    ("NATURGY",        "Hogar|Luz y gas",                    150),
    ("MOVISTAR",       "Hogar|Internet y teléfono",          150),
    ("VODAFONE",       "Hogar|Internet y teléfono",          150),
    ("NETFLIX",        "Educación y cultura|Suscripciones",  150),
    ("SPOTIFY",        "Educación y cultura|Suscripciones",  150),
    ("AMAZON",         "Compras|Compras (otros)",            130),
    ("VINTED",         "Compras|Compras (otros)",            130),
    ("CABIFY",         "Transporte|Transporte público",      140),
    ("UBER",           "Transporte|Transporte público",      140),
    ("FCIA",           "Salud|Farmacia",                     150),
    ("FARMACIA",       "Salud|Farmacia",                     150),
    ("CARITAS",        "Regalos y donaciones",               150),
    ("CRUZ ROJA",      "Regalos y donaciones",               150),
]


def seed_builtin_rules(cur: sqlite3.Cursor) -> None:
    """Carga reglas por defecto si aún no existen."""
    for pattern, hint, priority in _BUILTIN:
        existing = cur.execute(
            "SELECT 1 FROM category_rules WHERE pattern = ? AND source = 'builtin'",
            (pattern,),
        ).fetchone()
        if existing:
            continue
        cat_id = resolve_category(cur, hint)
        if cat_id is None:
            continue
        cur.execute(
            "INSERT OR IGNORE INTO category_rules(pattern, category_id, priority, source, hits) "
            "VALUES (?, ?, ?, 'builtin', 1)",
            (pattern, cat_id, priority),
        )
