"""
Auto-categorización local, 100% sin LLM.

Estrategia:
- Fuente A (bootstrap): los extractos de ING ya traen categoría → source_hint.
  Mapeamos a la jerarquía de la BD y, en paralelo, extraemos tokens de la
  descripción para generar reglas aprendidas ("MERCADONA" → Alimentación).
- Fuente B: el usuario puede recategorizar cualquier movimiento. Eso refuerza
  reglas y reentrena.
- Aplicación: para cada tx sin categoría, busca reglas por subcadena, elige la
  de mayor score (priority * hits).
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

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


# ====== Resolución de categoría destino en la BD ======

def resolve_category(cur: sqlite3.Cursor, hint: str | None,
                     default_kind: str = "expense") -> int | None:
    """
    hint = "Alimentación" o "Alimentación|Supermercados y alimentación"
    Devuelve id de la subcategoría si existe, si no el de la padre.
    Crea la jerarquía que falte respetando el nombre original del banco.
    """
    if not hint:
        return None
    parts = [p.strip() for p in hint.split("|") if p.strip()]
    if not parts:
        return None
    parent_name = parts[0]
    sub_name = parts[1] if len(parts) > 1 else None

    parent_row = cur.execute(
        "SELECT id FROM categories WHERE parent_id IS NULL AND LOWER(name) = LOWER(?)",
        (parent_name,),
    ).fetchone()
    if parent_row:
        parent_id = parent_row["id"]
    else:
        cur.execute(
            "INSERT INTO categories(name, kind) VALUES (?, ?)",
            (parent_name, default_kind),
        )
        parent_id = cur.lastrowid

    if parent_id and sub_name:
        sub_row = cur.execute(
            "SELECT id FROM categories WHERE parent_id = ? AND LOWER(name) = LOWER(?)",
            (parent_id, sub_name),
        ).fetchone()
        if sub_row:
            return sub_row["id"]
        # Creamos la subcategoría si no existe (ING tiene algunas que no sembramos)
        cur.execute(
            "INSERT OR IGNORE INTO categories(name, parent_id, kind) "
            "SELECT ?, ?, kind FROM categories WHERE id = ?",
            (sub_name, parent_id, parent_id),
        )
        sub_row = cur.execute(
            "SELECT id FROM categories WHERE parent_id = ? AND LOWER(name) = LOWER(?)",
            (parent_id, sub_name),
        ).fetchone()
        return sub_row["id"] if sub_row else parent_id

    return parent_id


def uncategorized_category_id(cur: sqlite3.Cursor) -> int:
    row = cur.execute(
        "SELECT id FROM categories WHERE parent_id IS NULL AND name = 'Sin categoría'"
    ).fetchone()
    return row["id"]


# ====== Aprendizaje de reglas ======

def learn_rules_from_known(cur: sqlite3.Cursor) -> int:
    """
    Recorre las transacciones que ya tienen category_id y actualiza
    category_rules con los tokens dominantes de cada descripción.
    Regla de confianza: un token genera regla si al menos el 70% de las
    transacciones donde aparece pertenecen a la misma categoría, y aparece >=2 veces.
    Devuelve el número de reglas creadas o actualizadas.
    """
    rows = cur.execute(
        "SELECT description, category_id FROM transactions "
        "WHERE category_id IS NOT NULL"
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
        if cat_hits / total < 0.70:
            continue
        # Si el token solo tiene 1 aparición, exigimos que sea suficientemente
        # distintivo (longitud) para no generar ruido.
        if total == 1 and len(tok) < 5:
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
    return created


# ====== Aplicación de reglas a transacciones sin categoría ======

def apply_rules_to_uncategorized(cur: sqlite3.Cursor) -> int:
    """
    Para cada transacción con category_id NULL, busca reglas cuyo patrón
    aparezca en la descripción. Se queda con la de mayor hits*priority.
    Devuelve el número de transacciones categorizadas.
    """
    rules = cur.execute(
        "SELECT pattern, category_id, priority, hits FROM category_rules"
    ).fetchall()
    if not rules:
        return 0

    uncat = cur.execute(
        "SELECT id, description FROM transactions WHERE category_id IS NULL"
    ).fetchall()

    updated = 0
    for tx in uncat:
        up = tx["description"].upper()
        best = None
        best_score = 0
        total_hits = 0
        for r in rules:
            if r["pattern"] in up:
                total_hits += r["hits"]
                score = r["priority"] * max(r["hits"], 1)
                if score > best_score:
                    best_score = score
                    best = r
        if best:
            # Confianza aproximada basada en hits del ganador frente al total coincidente
            conf = min(1.0, best["hits"] / max(total_hits, 1))
            cur.execute(
                "UPDATE transactions SET category_id = ?, auto_categorized = 1, "
                "confidence = ? WHERE id = ?",
                (best["category_id"], round(conf, 3), tx["id"]),
            )
            updated += 1
    return updated


def retrain_and_apply(cur: sqlite3.Cursor) -> tuple[int, int]:
    seed_builtin_rules(cur)
    created = learn_rules_from_known(cur)
    applied = apply_rules_to_uncategorized(cur)
    return created, applied


# ====== Reglas integradas para patrones bancarios comunes en España ======

_BUILTIN: list[tuple[str, str, int]] = [
    # (patrón, categoría hint, prioridad)
    ("BIZUM",          "Transferencias",                     150),
    ("NOMINA",         "Nómina y otras prestaciones|Nómina o Pensión", 200),
    ("PREST. DESEMPLEO", "Nómina y otras prestaciones|Desempleo",      200),
    ("DESEMPLEO",      "Nómina y otras prestaciones|Desempleo",       180),
    ("REINT.CAJERO",   "Sin categoría",                      140),
    ("REINTEGRO",      "Sin categoría",                      140),
    ("COMISIONES",     "Impuestos y comisiones|Comisiones bancarias", 180),
    ("COMISION",       "Impuestos y comisiones|Comisiones bancarias", 170),
    ("TRASPASO",       "Transferencias|Traspaso entre cuentas",        150),
    ("TRASPASOS",      "Transferencias|Traspaso entre cuentas",        150),
    ("MERCADONA",      "Alimentación|Supermercados y alimentación",   150),
    ("LIDL",           "Alimentación|Supermercados y alimentación",   150),
    ("ALCAMPO",        "Alimentación|Supermercados y alimentación",   150),
    ("CARREFOUR",      "Alimentación|Supermercados y alimentación",   150),
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
