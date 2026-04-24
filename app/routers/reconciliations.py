"""
Router /conciliar — reconciliación de cuentas contra el saldo del banco.

El usuario introduce el saldo que el banco dice tener a fecha X. TNT calcula
el saldo propio a esa fecha (saldo inicial + suma de movimientos hasta X) y
guarda la diferencia. Si difiere, es señal de que falta algún movimiento o
hay duplicados.
"""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from app.db import cursor
from app.services.analytics import account_balance_at

router = APIRouter()


@router.post("/conciliar/nueva")
def recon_create(
    account_id: int = Form(...),
    date: str = Form(...),
    bank_balance: float = Form(...),
    note: str = Form(""),
):
    with cursor() as cur:
        tnt_bal = account_balance_at(cur, account_id, date)
        diff = round(bank_balance - tnt_bal, 2)
        cur.execute(
            """INSERT INTO reconciliations
                 (account_id, date, bank_balance, tnt_balance, diff, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, date, round(bank_balance, 2), tnt_bal, diff, note.strip() or None),
        )
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/conciliar/{recon_id}/borrar")
def recon_delete(recon_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM reconciliations WHERE id = ?", (recon_id,))
    return RedirectResponse("/cuentas", status_code=303)
