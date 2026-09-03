"""
Router del panel principal: KPIs, donut por categoría, línea de saldo,
últimos movimientos, forecast y avisos.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import cursor
from app.services.analytics import (
    balance_series,
    by_category,
    month_income_expense,
    month_label,
    month_range,
    net_series,
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


def _parse_month_param(value: Optional[str]) -> Optional[date]:
    """Devuelve date(year, month, 1) si value es 'YYYY-MM' válido; si no, None."""
    if not value or len(value) < 7:
        return None
    try:
        y = int(value[:4])
        m = int(value[5:7])
        if 1 <= m <= 12 and 2000 <= y <= 2100:
            return date(y, m, 1)
    except (ValueError, TypeError):
        pass
    return None


def _adjacent_ym(ym: str, offset: int) -> str:
    """Devuelve YYYY-MM desplazado offset meses (1 o -1)."""
    y, m = int(ym[:4]), int(ym[5:7])
    m += offset
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, month: Optional[str] = None):
    with cursor() as cur:
        has_any = cur.execute("SELECT 1 FROM transactions LIMIT 1").fetchone()
        if not has_any:
            return templates.TemplateResponse(
                request, "dashboard_empty.html", {"active": "dashboard"}
            )

        balance = total_balance(cur)

        # Meses con datos para el selector (más reciente primero)
        available_months = [
            r["ym"] for r in cur.execute(
                "SELECT DISTINCT substr(date,1,7) AS ym FROM transactions "
                "ORDER BY ym DESC"
            ).fetchall()
        ]

        # Mes a mostrar:
        # 1º) ?month=YYYY-MM si llega válido,
        # 2º) mes actual si tiene movs,
        # 3º) último mes con datos como fallback.
        sel_date = _parse_month_param(month)
        latest_ym = available_months[0] if available_months else None
        cur_ym = date.today().strftime("%Y-%m")
        has_current_month = cur_ym in available_months

        if sel_date:
            ref = sel_date
            m_start, m_end = month_range(ref)
            p_start, p_end = prev_month_range(ref)
            showing_latest = False
        elif has_current_month:
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
        prev_cats = {c["id"]: c["total"] for c in by_category(cur, p_start, p_end, limit=50)}
        bal_series = balance_series(cur, months=6)
        net_ser = net_series(cur, [p["month"] for p in bal_series])

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

        # Desglose de cuentas activas para el lateral del panel.
        account_rows = cur.execute(
            """SELECT a.id, a.name,
                      a.initial_balance + COALESCE(SUM(t.amount), 0) AS bal
               FROM accounts a
               LEFT JOIN transactions t ON t.account_id = a.id
               WHERE a.archived = 0
               GROUP BY a.id
               ORDER BY bal DESC"""
        ).fetchall()

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

    # Cuentas: barra proporcional a la mayor, para comparar de un vistazo.
    top_bal = max((abs(r["bal"]) for r in account_rows), default=0) or 1.0
    accounts = [
        {
            "id": r["id"], "name": r["name"], "balance": r["bal"],
            "width": round(abs(r["bal"]) / top_bal * 100, 1),
            "color": _CATEGORY_COLORS[i % len(_CATEGORY_COLORS)],
        }
        for i, r in enumerate(account_rows)
    ]

    # Barras de gasto por categoría: peso relativo y variación mensual.
    cats_total = sum(c["total"] for c in cats) or 1.0
    cat_bars = []
    top_total = cats[0]["total"] if cats else 1.0
    for c in cats:
        before = prev_cats.get(c["id"])
        if before:
            delta = round((c["total"] - before) / before * 100, 1)
        else:
            delta = None          # categoría nueva este mes
        cat_bars.append({
            "id": c["id"], "name": c["name"], "total": c["total"],
            "pct": round(c["total"] / cats_total * 100),
            "width": round(c["total"] / (top_total or 1) * 100, 1),
            "delta": delta,
        })

    # Datos para Chart.js
    donut_labels = [c["name"] for c in cats]
    donut_values = [c["total"] for c in cats]
    donut_colors = _CATEGORY_COLORS[: len(cats)]

    line_labels = [month_label(p["month"]) for p in bal_series]
    line_values = [p["balance"] for p in bal_series]
    net_values = [p["net"] for p in net_ser]

    # Para el selector de mes
    current_ym = m_start[:7]
    months_for_selector = [
        {"ym": ym, "label": month_label(ym)} for ym in available_months
    ]
    # Permitimos avanzar/retroceder libremente, no solo entre meses con datos.
    prev_ym = _adjacent_ym(current_ym, -1)
    next_ym = _adjacent_ym(current_ym, +1)

    ctx = {
        "active": "dashboard",
        "balance": balance,
        "month_name": month_label(current_ym),
        "showing_latest": showing_latest,
        "current_ym": current_ym,
        "prev_ym": prev_ym,
        "next_ym": next_ym,
        "months_for_selector": months_for_selector,
        "cur_month": cur_month,
        "prev_month": prev_month,
        "delta_expense": delta_expense,
        "delta_income": delta_income,
        "last_transactions": last_transactions,
        "forecast": forecast,
        "anomalies": anomalies[:5],
        # .replace: estos JSON van con |safe dentro de <script>; escapar '<'
        # evita que un texto con '</script>' rompa/inyecte en la página.
        "donut_json": json.dumps({
            "labels": donut_labels,
            "values": donut_values,
            "colors": donut_colors,
        }).replace("<", "\\u003c"),
        "line_json": json.dumps({
            "labels": line_labels,
            "values": line_values,
        }).replace("<", "\\u003c"),
        "net_json": json.dumps({
            "labels": line_labels,
            "values": net_values,
        }).replace("<", "\\u003c"),
        "cat_bars": cat_bars,
        "accounts": accounts,
        "has_categories": len(cats) > 0,
        "has_series": len(bal_series) > 1,
    }
    return templates.TemplateResponse(request, "dashboard.html", ctx)
