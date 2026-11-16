"""
Router /movimientos — crear, editar y borrar un movimiento a mano.

La lista, los filtros y lo que se cambia sin salir de ella (la categoría y la
nota) están en transactions.py.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.db import cursor
from app.utils.forms import to_int_or_none

router = APIRouter()


def _manual_hash(account_id: int, tx_date: str, amount: float, description: str) -> str:
    """Hash estable para movimientos manuales. Prefijo 'manual:' evita colisión
    con los importados. Incluye un timestamp para permitir varios idénticos el
    mismo día (caso típico: dos cafés a 2 €)."""
    ts = datetime.now().isoformat()
    blob = f"manual|{account_id}|{tx_date}|{amount:.2f}|{description.strip().lower()}|{ts}"
    return "manual:" + hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _unlink_transfer_pair(cur, tx_id: int) -> None:
    """Si el movimiento estaba enlazado como traspaso, rompe el vínculo en
    ambos extremos. Se invoca antes de editar importe/fecha/cuenta o borrar."""
    row = cur.execute(
        "SELECT transfer_id FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if row and row["transfer_id"]:
        pair = row["transfer_id"]
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (tx_id,))
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (pair,))


@router.post("/movimientos/nuevo")
def transaction_create(
    request: Request,
    account_id: int = Form(...),
    date: str = Form(...),                      # noqa: A002 — shadow builtin, OK en handler
    amount: float = Form(...),
    description: str = Form(...),
    memo: str = Form(""),
    category_id: str = Form(""),
):
    """Crea un movimiento manual (gasto en efectivo, corrección, etc.)."""
    desc = (description or "").strip() or "(manual)"
    cat_id = to_int_or_none(category_id)
    with cursor() as cur:
        cur.execute(
            """INSERT INTO transactions(
                account_id, date, amount, description, memo,
                category_id, auto_categorized, confidence,
                transfer_id, payee, balance, source_hint, hash
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL, 'manual', ?)""",
            (
                account_id, date, amount, desc, (memo or "").strip() or None,
                cat_id, 1.0 if cat_id else None,
                _manual_hash(account_id, date, amount, desc),
            ),
        )
    return RedirectResponse("/movimientos", status_code=303)


@router.post("/movimientos/{tx_id}/editar")
def transaction_update(
    tx_id: int,
    account_id: int = Form(...),
    date: str = Form(...),                      # noqa: A002
    amount: float = Form(...),
    description: str = Form(...),
    memo: str = Form(""),
    category_id: str = Form(""),
):
    """Edita un movimiento existente. Si cambiaron campos clave (importe, fecha,
    cuenta), se rompe el enlace de traspaso por si ya no es simétrico."""
    desc = (description or "").strip() or "(manual)"
    cat_id = to_int_or_none(category_id)
    with cursor() as cur:
        old = cur.execute(
            "SELECT account_id, date, amount FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        if not old:
            return RedirectResponse("/movimientos", status_code=303)

        key_changed = (
            old["account_id"] != account_id
            or old["date"] != date
            or round(old["amount"], 2) != round(amount, 2)
        )
        if key_changed:
            _unlink_transfer_pair(cur, tx_id)

        cur.execute(
            """UPDATE transactions SET
                account_id = ?, date = ?, amount = ?,
                description = ?, memo = ?, category_id = ?,
                auto_categorized = CASE WHEN ? IS NULL THEN 0 ELSE auto_categorized END,
                confidence = CASE WHEN ? IS NULL THEN NULL ELSE confidence END,
                balance = NULL
               WHERE id = ?""",
            (
                account_id, date, amount, desc,
                (memo or "").strip() or None, cat_id,
                cat_id, cat_id, tx_id,
            ),
        )
    return RedirectResponse("/movimientos", status_code=303)


@router.post("/movimientos/{tx_id}/borrar")
def transaction_delete(tx_id: int):
    """Borra un movimiento. Si estaba enlazado como traspaso, desenlaza antes."""
    with cursor() as cur:
        _unlink_transfer_pair(cur, tx_id)
        cur.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return RedirectResponse("/movimientos", status_code=303)
