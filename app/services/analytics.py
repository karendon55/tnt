"""
Consultas agregadas para el dashboard y la búsqueda.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta


INVESTMENT_TYPE = "investment"


def last_valuation(cur: sqlite3.Cursor, account_id: int,
                   as_of: str | None = None) -> float | None:
    """Último valor declarado de una cuenta de inversión, o None si no hay.

    `as_of` limita la búsqueda a valoraciones anteriores o iguales a esa
    fecha, para poder reconstruir el histórico.
    """
    if as_of:
        row = cur.execute(
            "SELECT value FROM account_valuations WHERE account_id = ? AND date <= ? "
            "ORDER BY date DESC, id DESC LIMIT 1", (account_id, as_of),
        ).fetchone()
    else:
        row = cur.execute(
            "SELECT value FROM account_valuations WHERE account_id = ? "
            "ORDER BY date DESC, id DESC LIMIT 1", (account_id,),
        ).fetchone()
    return row["value"] if row else None


def contributed(cur: sqlite3.Cursor, account_id: int,
                as_of: str | None = None) -> float:
    """Aportado neto a una cuenta: saldo inicial más movimientos (las
    aportaciones suman, los reembolsos restan). Es lo que has puesto de tu
    bolsillo, sin contar lo que haya ganado o perdido."""
    if as_of:
        row = cur.execute(
            """SELECT a.initial_balance +
                      COALESCE((SELECT SUM(amount) FROM transactions
                                WHERE account_id = a.id AND date <= ?), 0) AS bal
               FROM accounts a WHERE a.id = ?""", (as_of, account_id),
        ).fetchone()
    else:
        row = cur.execute(
            """SELECT a.initial_balance + COALESCE(SUM(t.amount), 0) AS bal
               FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id
               WHERE a.id = ?""", (account_id,),
        ).fetchone()
    return round(row["bal"] if row and row["bal"] is not None else 0, 2)


def account_balance(cur: sqlite3.Cursor, account_id: int) -> float:
    """Saldo de una cuenta.

    En las cuentas de inversión manda la última valoración declarada; si
    aún no hay ninguna, se recurre a lo aportado.
    """
    row = cur.execute("SELECT type FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row and row["type"] == INVESTMENT_TYPE:
        value = last_valuation(cur, account_id)
        if value is not None:
            return round(value, 2)
    return contributed(cur, account_id)


def account_balance_at(cur: sqlite3.Cursor, account_id: int, as_of: str) -> float:
    """Saldo de una cuenta en una fecha dada (inclusive). Se usa en la
    reconciliación contra el saldo real del banco."""
    row = cur.execute("SELECT type FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row and row["type"] == INVESTMENT_TYPE:
        value = last_valuation(cur, account_id, as_of)
        if value is not None:
            return round(value, 2)
    return contributed(cur, account_id, as_of)


def total_balance(cur: sqlite3.Cursor, as_of: str | None = None) -> float:
    """Patrimonio: suma de las cuentas activas. Las de inversión aportan su
    valoración declarada en vez de la suma de sus movimientos."""
    total = 0.0
    for r in cur.execute(
        "SELECT id, type FROM accounts WHERE archived = 0"
    ).fetchall():
        if r["type"] == INVESTMENT_TYPE:
            value = last_valuation(cur, r["id"], as_of)
            if value is not None:
                total += value
                continue
        total += contributed(cur, r["id"], as_of)
    return round(total, 2)


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

    # Las cuentas de inversión no siguen la suma de movimientos: su valor lo
    # marca la última valoración declarada. Se restan de la serie acumulada y
    # se suman aparte, mes a mes, con la valoración vigente en cada cierre.
    inv = cur.execute(
        "SELECT id, initial_balance FROM accounts "
        "WHERE archived = 0 AND type = ?", (INVESTMENT_TYPE,),
    ).fetchall()
    inv_ids = [r["id"] for r in inv]
    if inv_ids:
        marks = ",".join("?" * len(inv_ids))
        initial -= sum(r["initial_balance"] for r in inv)
        inv_flow = cur.execute(
            f"""SELECT substr(date, 1, 7) AS ym, SUM(amount) AS delta
                FROM transactions WHERE account_id IN ({marks})
                GROUP BY ym""", inv_ids,
        ).fetchall()
        for r in inv_flow:
            delta_by_month[r["ym"]] = delta_by_month.get(r["ym"], 0) - r["delta"]

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
        total = running
        if inv_ids:
            # Último día del mes, para tomar la valoración vigente entonces
            nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
            month_end = (nxt - timedelta(days=1)).isoformat()
            for account_id in inv_ids:
                value = last_valuation(cur, account_id, month_end)
                total += value if value is not None else contributed(cur, account_id, month_end)
        result.append({"month": ym, "balance": round(total, 2)})
        m += 1
        if m == 13:
            m = 1
            y += 1
    return result[-months:]


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
