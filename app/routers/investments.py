"""
Router /inversiones — el valor de los fondos y planes, aparte del saldo.

Vivía dentro de /cuentas, que había crecido hasta 495 líneas mezclando cinco
cosas. Una cuenta de inversión sigue siendo una cuenta y aparece en Cuentas
con su saldo; lo que se mudó aquí es la gestión de su *valor*: lo aportado, lo
que vale hoy según el último informe y la diferencia entre ambos.

Las URLs de las acciones no cambian (/cuentas/{id}/valoracion y
/cuentas/valoracion/{id}/borrar): solo se ha mudado el código.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services.analytics import (
    INVESTMENT_TYPE, MONTHS_ES, contributed, last_valuation,
)
from app.templating import templates

router = APIRouter()


@router.get("/inversiones", response_class=HTMLResponse)
def investments_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            "SELECT id, name, bank, type, archived FROM accounts "
            "WHERE type = ? AND archived = 0 ORDER BY name", (INVESTMENT_TYPE,),
        ).fetchall()

        inv_accs = []
        for r in rows:
            puesto = contributed(cur, r["id"])
            valor = last_valuation(cur, r["id"])
            vals = [dict(v) for v in cur.execute(
                """SELECT id, date, value, note FROM account_valuations
                   WHERE account_id = ? ORDER BY date DESC, id DESC""",
                (r["id"],),
            ).fetchall()]
            gain = round((valor - puesto), 2) if valor is not None else None
            # Serie para el gráfico: valor declarado frente a lo aportado en
            # esa misma fecha. El hueco entre ambas líneas es la rentabilidad.
            serie = sorted(vals, key=lambda v: v["date"])
            chart = {
                "labels": [f'{MONTHS_ES[int(v["date"][5:7])][:3]} {v["date"][2:4]}'
                           for v in serie],
                "value": [v["value"] for v in serie],
                "contributed": [contributed(cur, r["id"], v["date"]) for v in serie],
            }
            inv_accs.append({
                "id": r["id"], "name": r["name"], "bank": r["bank"],
                "investment": {
                    "contributed": puesto,
                    "value": valor,
                    "gain": gain,
                    "gain_pct": (round(gain / puesto * 100, 2)
                                 if gain is not None and puesto else None),
                    "valuations": vals,
                    "chart_json": json.dumps(chart, ensure_ascii=False),
                    "has_chart": len(serie) >= 2,
                },
            })

    return templates.TemplateResponse(
        request, "investments.html",
        {
            "active": "investments",
            "inv_accs": inv_accs,
            "today_iso": date.today().isoformat(),
        },
    )


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
