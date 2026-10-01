"""
Reglas de transferencias externas.

Cuando un movimiento tiene una descripción que coincide con `pattern` de una
regla activa, se crea un movimiento espejo en `target_account_id` con el
importe opuesto y ambos se enlazan vía `transfer_id`. Así, aportaciones a
un plan de pensiones (u otros productos que no se descargan como extracto)
aparecen automáticamente como entradas en su cuenta de destino.

El patrón se busca en minúsculas como subcadena de la descripción.
Las reglas con `source_account_id = NULL` aplican a cualquier cuenta.
"""
from __future__ import annotations

import sqlite3

from app.importers.common import tx_hash


# Prefijo que marca el hash de movimientos creados por una regla externa.
# Así se evita colisionar con los hashes de los movimientos importados.
_MIRROR_PREFIX = "mirror:"


def apply_rules(cur: sqlite3.Cursor) -> int:
    """
    Aplica todas las reglas externas activas sobre los movimientos que aún
    no tienen `transfer_id` y cuya descripción coincide con algún patrón.

    Devuelve el número de movimientos espejo creados (no pares).
    """
    # Las reglas con importe van ANTES que las genéricas: si casan las dos, gana
    # la más específica, como en las reglas de categoría. Cada movimiento solo
    # se refleja una vez (al crear el espejo deja de tener transfer_id NULL),
    # así que el orden decide a qué cuenta va. El id desempata para que el
    # resultado no dependa de cómo devuelva SQLite las filas.
    rules = cur.execute(
        """SELECT id, pattern, source_account_id, target_account_id, amount
           FROM external_transfer_rules
           WHERE active = 1
           ORDER BY amount IS NULL, id"""
    ).fetchall()
    if not rules:
        return 0

    created = 0
    for rule in rules:
        pattern = (rule["pattern"] or "").strip().lower()
        if not pattern:
            continue

        # Movimientos candidatos: de la cuenta origen (o de cualquiera salvo la
        # destino, si la regla no fija origen), sin transfer_id, con el patrón
        # en la descripción, que NO sean ya un espejo y, si la regla lleva
        # importe, con ese importe exacto en valor absoluto: la apertura de un
        # depósito llega en negativo y su cancelación en positivo. Se compara a
        # céntimos porque un REAL puede traer ruido en el último decimal.
        if rule["source_account_id"] is None:
            origen_sql, origen = "account_id != ?", rule["target_account_id"]
        else:
            origen_sql, origen = "account_id = ?", rule["source_account_id"]
        candidates = cur.execute(
            f"""SELECT id, account_id, date, amount, description
                FROM transactions
                WHERE transfer_id IS NULL
                  AND {origen_sql}
                  AND hash NOT LIKE 'mirror:%'
                  AND LOWER(description) LIKE ?
                  AND (? IS NULL OR ROUND(ABS(amount), 2) = ROUND(?, 2))""",
            (origen, f"%{pattern}%", rule["amount"], rule["amount"]),
        ).fetchall()

        for tx in candidates:
            if _create_mirror(cur, tx, rule["target_account_id"]):
                created += 1

    return created


def _create_mirror(
    cur: sqlite3.Cursor, tx: sqlite3.Row, target_account_id: int
) -> bool:
    """Crea el movimiento espejo y enlaza ambos por transfer_id.
    Devuelve True si se creó (False si ya existía o hubo conflicto)."""
    # Hash estable y único para el espejo: permite re-ejecutar sin duplicar.
    mirror_hash = _MIRROR_PREFIX + tx_hash(
        iban=f"rule-target-{target_account_id}",
        date_iso=tx["date"],
        amount=-tx["amount"],
        description=tx["description"],
        balance=None,
    )

    # Si ya existe el espejo, sólo nos aseguramos del enlace y salimos.
    existing = cur.execute(
        "SELECT id FROM transactions WHERE hash = ?", (mirror_hash,)
    ).fetchone()
    if existing:
        if not _pair(cur, tx["id"], existing["id"]):
            return False
        return False  # no es nuevo

    cur.execute(
        """INSERT INTO transactions(
            account_id, date, amount, description, memo,
            category_id, auto_categorized, confidence,
            transfer_id, payee, balance, source_hint, hash
        ) VALUES (?, ?, ?, ?, ?, NULL, 0, NULL, ?, NULL, NULL, 'external_rule', ?)""",
        (
            target_account_id,
            tx["date"],
            -tx["amount"],                          # importe opuesto
            tx["description"],
            "Movimiento automático (regla externa)",
            tx["id"],                               # transfer_id apunta al origen
            mirror_hash,
        ),
    )
    mirror_id = cur.lastrowid
    cur.execute(
        "UPDATE transactions SET transfer_id = ? WHERE id = ?",
        (mirror_id, tx["id"]),
    )
    return True


def _pair(cur: sqlite3.Cursor, a_id: int, b_id: int) -> bool:
    """Asegura el enlace bidireccional entre dos movimientos si falta."""
    a = cur.execute(
        "SELECT transfer_id FROM transactions WHERE id = ?", (a_id,)
    ).fetchone()
    b = cur.execute(
        "SELECT transfer_id FROM transactions WHERE id = ?", (b_id,)
    ).fetchone()
    if not a or not b:
        return False
    changed = False
    if a["transfer_id"] != b_id:
        cur.execute(
            "UPDATE transactions SET transfer_id = ? WHERE id = ?", (b_id, a_id)
        )
        changed = True
    if b["transfer_id"] != a_id:
        cur.execute(
            "UPDATE transactions SET transfer_id = ? WHERE id = ?", (a_id, b_id)
        )
        changed = True
    return changed
