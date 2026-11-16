"""
Consultas agregadas por mes: ingresos y gastos, gasto por categoría y sus
series. Los saldos y la curva del patrimonio están en balances.py.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta


def month_range(today: date | None = None) -> tuple[str, str]:
    """Devuelve (primer_día_mes, último_día_mes) en ISO."""
    today = today or date.today()
    start = today.replace(day=1)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1, day=1)
    else:
        nxt = start.replace(month=start.month + 1, day=1)
    end = nxt - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def prev_month_range(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    first = today.replace(day=1)
    last_prev = first - timedelta(days=1)
    start_prev = last_prev.replace(day=1)
    return start_prev.isoformat(), last_prev.isoformat()


def month_income_expense(cur: sqlite3.Cursor, start: str, end: str) -> dict:
    """Sumas separando ingreso/gasto, excluyendo transferencias internas."""
    row = cur.execute(
        """SELECT
              COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
              COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS expense
           FROM transactions
           WHERE date BETWEEN ? AND ?
             AND transfer_id IS NULL""",
        (start, end),
    ).fetchone()
    return {
        "income": round(row["income"], 2),
        "expense": round(row["expense"], 2),
        "net": round(row["income"] + row["expense"], 2),
    }


def by_category(cur: sqlite3.Cursor, start: str, end: str, limit: int = 8) -> list[dict]:
    """
    Gasto (valor absoluto) agrupado por categoría padre en el rango.
    Excluye transferencias internas y categoría 'Sin categoría' (la mostramos aparte).
    """
    rows = cur.execute(
        """SELECT
             COALESCE(pc.id, c.id)   AS cat_id,
             COALESCE(pc.name, c.name) AS cat_name,
             SUM(-t.amount)          AS total
           FROM transactions t
           JOIN categories c ON c.id = t.category_id
           LEFT JOIN categories pc ON pc.id = c.parent_id
           WHERE t.date BETWEEN ? AND ?
             AND t.amount < 0
             AND t.transfer_id IS NULL
           GROUP BY COALESCE(pc.id, c.id)
           ORDER BY total DESC
           LIMIT ?""",
        (start, end, limit),
    ).fetchall()
    return [
        {"id": r["cat_id"], "name": r["cat_name"], "total": round(r["total"], 2)}
        for r in rows
    ]


def net_series(cur: sqlite3.Cursor, months: list[str]) -> list[dict]:
    """Ingresos, gastos y neto de cada mes indicado (formato 'YYYY-MM').

    Recibe la lista de meses para poder alinearse exactamente con la serie
    de saldo del panel y que el eje X no cambie al alternar los gráficos.
    Excluye traspasos internos, igual que `month_income_expense`.
    """
    if not months:
        return []
    rows = cur.execute(
        """SELECT substr(date, 1, 7) AS ym,
                  COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                  COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS expense
           FROM transactions
           WHERE transfer_id IS NULL
           GROUP BY ym"""
    ).fetchall()
    by_month = {r["ym"]: r for r in rows}
    out = []
    for ym in months:
        r = by_month.get(ym)
        income = r["income"] if r else 0.0
        expense = r["expense"] if r else 0.0
        out.append({
            "month": ym,
            "income": round(income, 2),
            "expense": round(expense, 2),
            "net": round(income + expense, 2),
        })
    return out


def category_monthly_series(
    cur: sqlite3.Cursor,
    months: int = 12,
    kind: str = "expense",
    top_n: int = 6,
) -> dict:
    """
    Evolución mensual del gasto (o ingreso) por categoría padre.

    Devuelve:
      {
        "months": ["2025-06", ..., "2026-05"],   # ventana de N meses hasta hoy
        "series": [{"id": int, "name": str, "values": [float, ...]}, ...],
                                                  # ordenadas por total desc
        "others": [float, ...] | None,            # suma de las que no entran en top_n
      }

    `kind` es 'expense' (suma -amount cuando amount<0) o 'income' (amount>0).
    Excluye transferencias internas (transfer_id NOT NULL).
    """
    today = date.today()
    # Ventana cerrada de N meses contando hacia atrás desde el mes actual.
    ym_list: list[str] = []
    y, m = today.year, today.month
    for _ in range(months):
        ym_list.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    ym_list.reverse()

    if kind == "income":
        amount_expr = "SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END)"
    else:
        amount_expr = "SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END)"

    rows = cur.execute(
        f"""SELECT
              COALESCE(pc.id, c.id)   AS cat_id,
              COALESCE(pc.name, c.name) AS cat_name,
              substr(t.date, 1, 7)    AS ym,
              {amount_expr}           AS total
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            LEFT JOIN categories pc ON pc.id = c.parent_id
            WHERE t.transfer_id IS NULL
              AND substr(t.date, 1, 7) BETWEEN ? AND ?
            GROUP BY cat_id, cat_name, ym
            HAVING total > 0""",
        (ym_list[0], ym_list[-1]),
    ).fetchall()

    cat_totals: dict[int, dict] = {}
    for r in rows:
        cid = r["cat_id"]
        cat_totals.setdefault(cid, {"id": cid, "name": r["cat_name"], "by_ym": {}})
        cat_totals[cid]["by_ym"][r["ym"]] = float(r["total"] or 0)

    ranked = sorted(
        cat_totals.values(),
        key=lambda c: sum(c["by_ym"].values()),
        reverse=True,
    )
    top = ranked[:top_n]
    rest = ranked[top_n:]

    series = [
        {
            "id": c["id"],
            "name": c["name"],
            "values": [round(c["by_ym"].get(ym, 0), 2) for ym in ym_list],
        }
        for c in top
    ]
    others = None
    if rest:
        others = [
            round(sum(c["by_ym"].get(ym, 0) for c in rest), 2)
            for ym in ym_list
        ]
    return {"months": ym_list, "series": series, "others": others}


MONTHS_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def month_label(ym: str) -> str:
    """'2026-03' -> 'marzo 2026'"""
    y, m = ym.split("-")
    return f"{MONTHS_ES[int(m)]} {y}"
