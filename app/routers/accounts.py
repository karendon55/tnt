"""
Router /cuentas — CRUD simple. El saldo se calcula desde las transacciones.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services.analytics import account_balance
from app.templating import templates

router = APIRouter()


@router.get("/cuentas", response_class=HTMLResponse)
def accounts_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            "SELECT id, name, bank, iban, type, initial_balance, currency, "
            "archived FROM accounts ORDER BY archived, name"
        ).fetchall()
        accounts = []
        for r in rows:
            bal = account_balance(cur, r["id"]) if not r["archived"] else None
            tx_count = cur.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE account_id = ?",
                (r["id"],),
            ).fetchone()["n"]
            accounts.append({
                "id": r["id"], "name": r["name"], "bank": r["bank"],
                "iban": r["iban"], "type": r["type"],
                "initial_balance": r["initial_balance"],
                "currency": r["currency"] or "EUR",
                "archived": bool(r["archived"]),
                "balance": bal,
                "tx_count": tx_count,
            })

    return templates.TemplateResponse(
        request, "accounts.html",
        {"active": "accounts", "accounts": accounts},
    )


@router.post("/cuentas/nueva")
def accounts_create(
    name: str = Form(...),
    bank: str = Form(""),
    iban: str = Form(""),
    initial_balance: float = Form(0.0),
    type: str = Form("bank"),
):
    with cursor() as cur:
        cur.execute(
            "INSERT INTO accounts(name, bank, iban, type, initial_balance, currency) "
            "VALUES (?, ?, ?, ?, ?, 'EUR')",
            (name.strip(), bank.strip(), iban.strip(), type, initial_balance),
        )
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/cuentas/{account_id}/editar")
def accounts_update(
    account_id: int,
    name: str = Form(...),
    bank: str = Form(""),
    iban: str = Form(""),
    initial_balance: float = Form(0.0),
    type: str = Form("bank"),
):
    with cursor() as cur:
        cur.execute(
            "UPDATE accounts SET name=?, bank=?, iban=?, initial_balance=?, type=? "
            "WHERE id=?",
            (name.strip(), bank.strip(), iban.strip(), initial_balance, type, account_id),
        )
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/cuentas/{account_id}/archivar")
def accounts_archive(account_id: int):
    with cursor() as cur:
        cur.execute("UPDATE accounts SET archived = 1 WHERE id = ?", (account_id,))
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/cuentas/{account_id}/restaurar")
def accounts_restore(account_id: int):
    with cursor() as cur:
        cur.execute("UPDATE accounts SET archived = 0 WHERE id = ?", (account_id,))
    return RedirectResponse("/cuentas", status_code=303)
