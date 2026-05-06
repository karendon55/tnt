"""
Consultas agregadas para el dashboard y la búsqueda.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta


def account_balance(cur: sqlite3.Cursor, account_id: int) -> float:
    row = cur.execute(
        """SELECT a.initial_balance + COALESCE(SUM(t.amount), 0) AS bal
           FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id
           WHERE a.id = ?""",
        (account_id,),
    ).fetchone()
    return round(row["bal"] if row and row["bal"] is not None else 0, 2)


def account_balance_at(cur: sqlite3.Cursor, account_id: int, as_of: str) -> float:
    """Saldo de una cuenta en una fecha dada (inclusive). Se usa en la
    reconciliación contra el saldo real del banco."""
    row = cur.execute(
        """SELECT a.initial_balance +
                  COALESCE((SELECT SUM(amount) FROM transactions
                            WHERE account_id = a.id AND date <= ?), 0) AS bal
           FROM accounts a WHERE a.id = ?""",
        (as_of, account_id),
    ).fetchone()
    return round(row["bal"] if row and row["bal"] is not None else 0, 2)


def total_balance(cur: sqlite3.Cursor) -> float:
    initial = cur.execute(
        "SELECT COALESCE(SUM(initial_balance), 0) AS ib FROM accounts WHERE archived = 0"
    ).fetchone()["ib"]
    flow = cur.execute(
        """SELECT COALESCE(SUM(t.amount), 0) AS f
           FROM transactions t JOIN accounts a ON a.id = t.account_id
           WHERE a.archived = 0"""
    ).fetchone()["f"]
    return round(initial + flow, 2)


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


def balance_series(cur: sqlite3.Cursor, months: int = 6) -> list[dict]:
    """Saldo acumulado al final de cada mes durante los últimos N meses."""
    today = date.today()
    # Saldo inicial total
    ib_row = cur.execute(
        "SELECT COALESCE(SUM(initial_balance), 0) AS ib FROM accounts WHERE archived = 0"
    ).fetchone()
    initial = ib_row["ib"] or 0

    # Flujo acumulado por mes
    rows = cur.execute(
        """SELECT substr(date, 1, 7) AS ym, SUM(amount) AS delta
           FROM transactions
           GROUP BY ym ORDER BY ym"""
    ).fetchall()
    delta_by_month = {r["ym"]: r["delta"] for r in rows}

    # Construir series
    result = []
    running = initial
    # Vamos mes a mes desde el más antiguo al presente
    if not rows:
        return []
    start_ym = rows[0]["ym"]
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    while (y, m) <= (today.year, today.month):
        ym = f"{y:04d}-{m:02d}"
        running += delta_by_month.get(ym, 0)
        result.append({"month": ym, "balance": round(running, 2)})
        m += 1
        if m == 13:
            m = 1
            y += 1
    return result[-months:]


def monthly_expense_series(cur: sqlite3.Cursor, months: int = 12) -> list[dict]:
    """Gasto (valor absoluto) por mes."""
    rows = cur.execute(
        """SELECT substr(date, 1, 7) AS ym, SUM(-amount) AS total
           FROM transactions
           WHERE amount < 0 AND transfer_id IS NULL
           GROUP BY ym ORDER BY ym"""
    ).fetchall()
    return [{"month": r["ym"], "total": round(r["total"], 2)} for r in rows[-months:]]


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


def category_tree(cur: sqlite3.Cursor) -> list[dict]:
    cats = cur.execute(
        "SELECT id, name, parent_id, kind FROM categories ORDER BY parent_id IS NOT NULL, name"
    ).fetchall()
    by_parent: dict[int | None, list] = {}
    by_id: dict[int, dict] = {}
    for c in cats:
        d = {"id": c["id"], "name": c["name"], "parent_id": c["parent_id"],
             "kind": c["kind"], "children": []}
        by_id[c["id"]] = d
        by_parent.setdefault(c["parent_id"], []).append(d)
    tree = by_parent.get(None, [])
    for parent in tree:
        parent["children"] = by_parent.get(parent["id"], [])
    return tree


MONTHS_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def month_label(ym: str) -> str:
    """'2026-03' -> 'marzo 2026'"""
    y, m = ym.split("-")
    return f"{MONTHS_ES[int(m)]} {y}"
