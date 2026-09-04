"""
Router /cuentas — CRUD simple. El saldo se calcula desde las transacciones.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.importers.common import normalize_iban
from app.services.analytics import (
    INVESTMENT_TYPE, account_balance, contributed, last_valuation,
)
from app.templating import templates

router = APIRouter()


@router.get("/cuentas", response_class=HTMLResponse)
def accounts_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            "SELECT id, name, bank, iban, type, initial_balance, currency, "
            "archived FROM accounts ORDER BY archived, name"
        ).fetchall()
        today = date.today()
        accounts = []
        for r in rows:
            bal = account_balance(cur, r["id"]) if not r["archived"] else None
            tx_count = cur.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE account_id = ?",
                (r["id"],),
            ).fetchone()["n"]
            # Historial de reconciliaciones de esta cuenta
            rec_rows = cur.execute(
                """SELECT id, date, bank_balance, tnt_balance, diff, note, created_at
                   FROM reconciliations WHERE account_id = ?
                   ORDER BY date DESC, id DESC""",
                (r["id"],),
            ).fetchall()
            recons = [dict(x) for x in rec_rows]
            last_recon = recons[0] if recons else None
            days_since = None
            if last_recon:
                try:
                    last_date = date.fromisoformat(last_recon["date"])
                    days_since = (today - last_date).days
                except Exception:
                    days_since = None
            # Una cuenta de inversión enseña tres cifras que no son la misma:
            # lo aportado, lo que vale hoy y la diferencia entre ambas.
            investment = None
            if r["type"] == INVESTMENT_TYPE:
                puesto = contributed(cur, r["id"])
                valor = last_valuation(cur, r["id"])
                vals = [dict(v) for v in cur.execute(
                    """SELECT id, date, value, note FROM account_valuations
                       WHERE account_id = ? ORDER BY date DESC, id DESC""",
                    (r["id"],),
                ).fetchall()]
                gain = round((valor - puesto), 2) if valor is not None else None
                investment = {
                    "contributed": puesto,
                    "value": valor,
                    "gain": gain,
                    "gain_pct": (round(gain / puesto * 100, 2)
                                 if gain is not None and puesto else None),
                    "valuations": vals,
                }

            accounts.append({
                "id": r["id"], "name": r["name"], "bank": r["bank"],
                "investment": investment,
                "iban": r["iban"], "type": r["type"],
                "initial_balance": r["initial_balance"],
                "currency": r["currency"] or "EUR",
                "archived": bool(r["archived"]),
                "balance": bal,
                "tx_count": tx_count,
                "recons": recons,
                "last_recon": last_recon,
                "days_since_recon": days_since,
            })

        # Reglas de transferencias externas (plan de pensiones, etc.)
        rule_rows = cur.execute(
            """SELECT r.id, r.pattern, r.source_account_id, r.target_account_id,
                      r.active, r.note,
                      sa.name AS source_name, ta.name AS target_name
               FROM external_transfer_rules r
               LEFT JOIN accounts sa ON sa.id = r.source_account_id
               LEFT JOIN accounts ta ON ta.id = r.target_account_id
               ORDER BY r.active DESC, r.pattern"""
        ).fetchall()
        rules = [dict(r) for r in rule_rows]

    return templates.TemplateResponse(
        request, "accounts.html",
        {
            "active": "accounts",
            "accounts": accounts,
            "rules": rules,
            "today_iso": today.isoformat(),
        },
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
            (name.strip(), bank.strip(), normalize_iban(iban), type, initial_balance),
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
            (name.strip(), bank.strip(), normalize_iban(iban), initial_balance, type, account_id),
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


@router.post("/cuentas/{account_id}/valoracion")
def valuation_create(
    account_id: int,
    date: str = Form(...),
    value: float = Form(...),
    note: str = Form(""),
):
    """Registra el valor que la entidad declara para una cuenta de inversión.

    Si ya hay una valoración con esa fecha se sustituye, para poder corregir
    una cifra mal tecleada sin tener que borrarla antes.
    """
    with cursor() as cur:
        cur.execute(
            """INSERT INTO account_valuations(account_id, date, value, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id, date) DO UPDATE
                 SET value = excluded.value, note = excluded.note""",
            (account_id, date.strip(), value, note.strip() or None),
        )
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/cuentas/valoracion/{valuation_id}/borrar")
def valuation_delete(valuation_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM account_valuations WHERE id = ?", (valuation_id,))
    return RedirectResponse("/cuentas", status_code=303)
