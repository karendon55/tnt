"""
Router del panel principal: KPIs, donut por categoría, línea de saldo,
últimos movimientos, forecast y avisos.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import cursor
from app.services.analytics import (
    balance_series,
    by_category,
    month_income_expense,
    month_label,
    month_range,
    prev_month_range,
    total_balance,
)
from app.services.forecast import forecast_next_month
from app.services.recurring import detect_anomalies
from app.templating import templates

router = APIRouter()


_CATEGORY_COLORS = [
    "#e10600", "#ff6b35", "#f7b801", "#4ade80", "#38bdf8",
    "#a78bfa", "#f472b6", "#94a3b8", "#c0c0c0", "#fb923c",
]


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with cursor() as cur:
        has_any = cur.execute("SELECT 1 FROM transactions LIMIT 1").fetchone()
        if not has_any:
            return templates.TemplateResponse(
                request, "dashboard_empty.html", {"active": "dashboard"}
            )

        balance = total_balance(cur)

        # Si el mes actual no tiene movs, mostramos el último mes con datos
        latest_ym_row = cur.execute(
            "SELECT MAX(substr(date,1,7)) AS ym FROM transactions"
        ).fetchone()
        latest_ym = latest_ym_row["ym"] if latest_ym_row else None
        cur_ym = date.today().strftime("%Y-%m")
        has_current_month = cur.execute(
            "SELECT 1 FROM transactions WHERE substr(date,1,7) = ? LIMIT 1",
            (cur_ym,),
        ).fetchone() is not None

        if has_current_month:
            m_start, m_end = month_range()
            p_start, p_end = prev_month_range()
            showing_latest = False
        else:
            y, m = int(latest_ym[:4]), int(latest_ym[5:7])
            ref = date(y, m, 1)
            m_start, m_end = month_range(ref)
            p_start, p_end = prev_month_range(ref)
            showing_latest = True

        cur_month = month_income_expense(cur, m_start, m_end)
        prev_month = month_income_expense(cur, p_start, p_end)

        cats = by_category(cur, m_start, m_end, limit=8)
        bal_series = balance_series(cur, months=6)

        last_rows = cur.execute(
            """SELECT t.id, t.date, t.amount, t.description,
                      t.transfer_id, t.balance,
                      c.name AS cat_name,
                      pc.name AS parent_cat_name
               FROM transactions t
               LEFT JOIN categories c  ON c.id  = t.category_id
               LEFT JOIN categories pc ON pc.id = c.parent_id
               ORDER BY t.date DESC, t.id DESC
               LIMIT 10"""
        ).fetchall()
        last_transactions = [
            {
                "id": r["id"],
                "date": r["date"],
                "amount": r["amount"],
                "description": r["description"],
                "is_transfer": r["transfer_id"] is not None,
                "category": r["parent_cat_name"] or r["cat_name"] or "Sin categoría",
            }
            for r in last_rows
        ]

        forecast = forecast_next_month(cur)
        anomalies = detect_anomalies(cur)

    # Delta vs mes anterior
    delta_expense = None
    if prev_month["expense"]:
        delta_expense = round(
            (cur_month["expense"] - prev_month["expense"]) / abs(prev_month["expense"]) * 100, 1
        )
    delta_income = None
    if prev_month["income"]:
        delta_income = round(
            (cur_month["income"] - prev_month["income"]) / abs(prev_month["income"]) * 100, 1
        )

    # Datos para Chart.js
    donut_labels = [c["name"] for c in cats]
    donut_values = [c["total"] for c in cats]
    donut_colors = _CATEGORY_COLORS[: len(cats)]

    line_labels = [month_label(p["month"]) for p in bal_series]
    line_values = [p["balance"] for p in bal_series]

    ctx = {
        "active": "dashboard",
        "balance": balance,
        "month_name": month_label(m_start[:7]),
        "showing_latest": showing_latest,
        "cur_month": cur_month,
        "prev_month": prev_month,
        "delta_expense": delta_expense,
        "delta_income": delta_income,
        "last_transactions": last_transactions,
        "forecast": forecast,
        "anomalies": anomalies[:5],
        "donut_json": json.dumps({
            "labels": donut_labels,
            "values": donut_values,
            "colors": donut_colors,
        }),
        "line_json": json.dumps({
            "labels": line_labels,
            "values": line_values,
        }),
        "has_categories": len(cats) > 0,
        "has_series": len(bal_series) > 1,
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)
