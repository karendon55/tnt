"""
Forecast: proyecta el saldo al final del mes siguiente combinando
transacciones recurrentes + tendencia del gasto variable.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from statistics import mean

from app.services.analytics import total_balance
from app.services.recurring import find_recurring

# A la previsión le vale con que algo se repita dos veces: es una estimación,
# no un aviso.
MIN_RECURRENCIAS = 2


def forecast_next_month(cur: sqlite3.Cursor,
                        recurrings: list | None = None) -> dict:
    """Devuelve un dict con:
       - current_balance: saldo hoy
       - recurring_net: suma neta estimada de recurrentes para el mes siguiente
       - variable_net: estimación del gasto variable (media 3 últimos meses)
       - projected_balance: saldo proyectado fin del mes siguiente
       - detail: lista de recurrentes usados

    `recurrings` permite pasarle los grupos ya calculados, para no buscarlos
    dos veces en la misma página (ver `detect_anomalies`). Si vienen, tienen
    que haberse buscado con `MIN_RECURRENCIAS` o menos.
    """
    current = total_balance(cur)

    if recurrings is None:
        recurrings = find_recurring(cur, min_occurrences=MIN_RECURRENCIAS)
    recurring_monthly = [r for r in recurrings if r.kind == "monthly"]
    recurring_quarterly = [r for r in recurrings if r.kind == "quarterly"]

    next_month_start = _next_month_first(date.today())
    # Recurrentes mensuales contribuyen con su media
    recurring_net = sum(r.avg_amount for r in recurring_monthly)
    # Trimestrales: 1/3 del efecto mensualizado
    recurring_net += sum(r.avg_amount / 3 for r in recurring_quarterly)

    # Gasto variable: gasto no recurrente en los últimos 3 meses, media mensual.
    # Se le pasan los mensuales ya calculados: buscarlos otra vez es releer la
    # tabla de movimientos entera y reagruparla, para el mismo resultado.
    variable_net = _variable_net_estimate(cur, recurring_monthly)

    projected = round(current + recurring_net + variable_net, 2)

    return {
        "current_balance": current,
        "recurring_net": round(recurring_net, 2),
        "variable_net": round(variable_net, 2),
        "projected_balance": projected,
        "forecast_for": next_month_start.isoformat(),
        "recurring_items": [
            {
                "payee": r.payee_key,
                "amount": r.avg_amount,
                "kind": r.kind,
                "description": r.description_sample,
            }
            for r in recurring_monthly + recurring_quarterly
        ],
    }


def _next_month_first(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _variable_net_estimate(cur: sqlite3.Cursor, recurring_monthly: list) -> float:
    """Media del neto NO recurrente en los últimos 3 meses.

    `recurring_monthly` son los grupos mensuales ya calculados por quien llama."""
    today = date.today()
    three_months_ago = today - timedelta(days=93)
    rows = cur.execute(
        """SELECT substr(date, 1, 7) AS ym, SUM(amount) AS total
           FROM transactions
           WHERE transfer_id IS NULL
             AND date >= ?
           GROUP BY ym
           ORDER BY ym""",
        (three_months_ago.isoformat(),),
    ).fetchall()
    if not rows:
        return 0.0
    # Resta recurrentes estimados
    recurring_per_month = sum(r.avg_amount for r in recurring_monthly)
    deltas = [r["total"] - recurring_per_month for r in rows]
    return mean(deltas) if deltas else 0.0
