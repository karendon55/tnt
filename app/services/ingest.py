"""
Ingestor: toma un ParsedExtract y lo inserta en la BD con deduplicación,
asignación de categoría vía source_hint, y detección de transferencias internas.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from app.importers.common import ParsedExtract, tx_hash
from app.services.categorizer import resolve_category
from app.services.external_transfers import apply_rules as apply_external_rules


@dataclass
class ImportResult:
    account_id: int
    account_name: str
    total_rows: int
    inserted: int
    duplicates: int
    categorized_from_hint: int
    transfers_linked: int


def ensure_account(cur: sqlite3.Cursor, extract: ParsedExtract) -> tuple[int, str]:
    """Devuelve (account_id, account_name). Crea la cuenta si no existe."""
    row = cur.execute(
        "SELECT id, name FROM accounts WHERE iban = ? AND iban != ''",
        (extract.iban,),
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # Sin IBAN: intentar por nombre
    row = cur.execute(
        "SELECT id, name FROM accounts WHERE name = ?",
        (extract.account_name,),
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # Initial balance: si el extracto trae saldo, deducimos el saldo inicial
    # a partir del primer movimiento (saldo - importe). Si no, 0.
    initial = 0.0
    if extract.transactions:
        last = extract.transactions[-1]  # normalmente ordenado desc → el último es el más antiguo
        if last.balance is not None:
            initial = round(last.balance - last.amount, 2)

    cur.execute(
        "INSERT INTO accounts(name, bank, iban, type, initial_balance, currency) "
        "VALUES (?, ?, ?, 'bank', ?, ?)",
        (extract.account_name, extract.bank, extract.iban, initial, extract.currency),
    )
    return cur.lastrowid, extract.account_name


def ingest(cur: sqlite3.Cursor, extract: ParsedExtract) -> ImportResult:
    account_id, account_name = ensure_account(cur, extract)

    total = len(extract.transactions)
    inserted = 0
    dupes = 0
    cat_from_hint = 0

    for tx in extract.transactions:
        date_iso = tx.date.isoformat()
        h = tx_hash(
            iban=extract.iban,
            date_iso=date_iso,
            amount=tx.amount,
            description=tx.description,
            balance=tx.balance,
        )
        exists = cur.execute(
            "SELECT 1 FROM transactions WHERE hash = ?", (h,)
        ).fetchone()
        if exists:
            dupes += 1
            continue

        category_id = resolve_category(cur, tx.source_hint)
        if category_id:
            cat_from_hint += 1

        cur.execute(
            """INSERT INTO transactions(
                account_id, date, value_date, amount, description, memo,
                category_id, auto_categorized, confidence, payee, balance,
                source_hint, hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                account_id, date_iso,
                tx.value_date.isoformat() if tx.value_date else None,
                tx.amount, tx.description, tx.memo,
                category_id,
                1 if category_id and tx.source_hint else 0,
                1.0 if category_id and tx.source_hint else None,
                None,
                tx.balance,
                tx.source_hint,
                h,
            ),
        )
        inserted += 1

    transfers = _link_internal_transfers(cur)
    # Reglas externas: crean espejos (p. ej. aportaciones a plan de pensiones)
    mirrors = apply_external_rules(cur)
    transfers += mirrors * 2  # cada espejo enlaza 2 movimientos

    return ImportResult(
        account_id=account_id,
        account_name=account_name,
        total_rows=total,
        inserted=inserted,
        duplicates=dupes,
        categorized_from_hint=cat_from_hint,
        transfers_linked=transfers,
    )


def _link_internal_transfers(cur: sqlite3.Cursor, window_days: int = 3) -> int:
    """
    Empareja dos transacciones de cuentas distintas con importes opuestos
    dentro de una ventana temporal corta. Caso típico: Bizum enviado a
    otra cuenta propia, o traspaso entre cuentas.
    """
    # Sólo hacemos un pase sobre las todavía sin transfer_id asignado
    rows = cur.execute(
        """SELECT id, account_id, date, amount, description
           FROM transactions
           WHERE transfer_id IS NULL
           ORDER BY date"""
    ).fetchall()

    by_account: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)

    linked = 0
    seen: set[int] = set()
    for i, a in enumerate(rows):
        if a["id"] in seen:
            continue
        for b in rows[i + 1:]:
            if b["id"] in seen:
                continue
            if a["account_id"] == b["account_id"]:
                continue
            if round(a["amount"] + b["amount"], 2) != 0.0:
                continue
            # Ventana temporal
            from datetime import date as _date
            da = _date.fromisoformat(a["date"])
            db = _date.fromisoformat(b["date"])
            if abs((db - da).days) > window_days:
                continue
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?",
                        (b["id"], a["id"]))
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?",
                        (a["id"], b["id"]))
            seen.add(a["id"])
            seen.add(b["id"])
            linked += 2
            break
    return linked
