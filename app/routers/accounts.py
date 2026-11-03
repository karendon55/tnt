"""
Router /cuentas — alta, baja y conciliación. El saldo sale de los movimientos.

Lo que era de inversiones (valor, aportado, valoraciones) vive en
app/routers/investments.py, y las reglas de transferencias externas en
app/routers/rules.py: esta pantalla se había convertido en un cajón de sastre
de 495 líneas.
"""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.importers.common import normalize_iban
from app.services.analytics import balances_by_account
from app.templating import templates

router = APIRouter()

_TIPOS = {"bank": "Cuenta bancaria", "investment": "Inversión", "cash": "Efectivo",
          "credit": "Tarjeta de crédito"}


def subtitulo_cuenta(nombre: str, banco: str | None, iban: str | None, tipo: str) -> str:
    """La segunda línea de la fila de una cuenta (design-system.md, referencia 3):
    banco, tipo y los cuatro últimos dígitos del IBAN, cada uno solo si el nombre no
    lo dice ya, por palabra entera («ING» no está en «Parking»). El tipo va cuando no
    es una cuenta de banco, o cuando no queda nada más que decir."""
    def en_el_nombre(trozo: str) -> bool:
        return re.search(rf"(?<!\w){re.escape(trozo)}(?!\w)", nombre, re.IGNORECASE) is not None

    partes = []
    if banco and not en_el_nombre(banco.strip()):
        partes.append(banco.strip())
    if tipo != "bank":
        partes.append(_TIPOS.get(tipo, tipo))
    digitos = re.sub(r"\s+", "", iban or "")[-4:]
    if digitos and not en_el_nombre(digitos):
        partes.append(f"····{digitos}")
    return " · ".join(partes) or _TIPOS.get(tipo, tipo)


@router.get("/cuentas", response_class=HTMLResponse)
def accounts_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            "SELECT id, name, bank, iban, type, initial_balance, currency, "
            "archived FROM accounts ORDER BY archived, name"
        ).fetchall()
        today = date.today()

        # Todo de una vez, no cuenta por cuenta: con nueve cuentas esta página
        # hacía 39 consultas y con cien, 403.
        saldos = balances_by_account(cur)
        movimientos = {
            x["account_id"]: x["n"] for x in cur.execute(
                "SELECT account_id, COUNT(*) AS n FROM transactions GROUP BY account_id")
        }
        conciliaciones: dict[int, list[dict]] = {}
        for x in cur.execute(
            """SELECT id, account_id, date, bank_balance, tnt_balance, diff, note,
                      created_at
               FROM reconciliations ORDER BY account_id, date DESC, id DESC"""
        ):
            conciliaciones.setdefault(x["account_id"], []).append(dict(x))

        accounts = []
        for r in rows:
            bal = saldos.get(r["id"], 0.0) if not r["archived"] else None
            tx_count = movimientos.get(r["id"], 0)
            recons = conciliaciones.get(r["id"], [])
            last_recon = recons[0] if recons else None
            days_since = None
            if last_recon:
                try:
                    last_date = date.fromisoformat(last_recon["date"])
                    days_since = (today - last_date).days
                except Exception:
                    days_since = None
            accounts.append({
                "id": r["id"], "name": r["name"], "bank": r["bank"],
                "iban": r["iban"], "type": r["type"],
                "subtitulo": subtitulo_cuenta(r["name"], r["bank"], r["iban"], r["type"]),
                "initial_balance": r["initial_balance"],
                "currency": r["currency"] or "EUR",
                "archived": bool(r["archived"]),
                "balance": bal,
                "tx_count": tx_count,
                "recons": recons,
                "last_recon": last_recon,
                "days_since_recon": days_since,
            })


    return templates.TemplateResponse(
        request, "accounts.html",
        {
            "active": "accounts",
            "accounts": accounts,
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
