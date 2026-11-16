"""
Saldos: el de una cuenta, el de todas, el patrimonio y su curva mes a mes.

Una cuenta normal vale su saldo inicial más sus movimientos. Una de inversión
vale su última valoración declarada (un fondo cambia de valor sin que haya
movimientos) y, mientras no tenga ninguna, lo aportado. Esa regla vive aquí:
quien necesita un saldo se lo pide a este módulo.
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


def balances_by_account(cur: sqlite3.Cursor,
                        as_of: str | None = None) -> dict[int, float]:
    """El saldo de TODAS las cuentas, en dos consultas en vez de dos por cuenta.

    Mismas reglas que `account_balance`, que sigue estando para cuando solo
    hace falta una: en las cuentas de inversión manda la última valoración
    declarada y, si no hay ninguna, lo aportado. `as_of` corta por fecha,
    igual que en `account_balance_at`.

    Existe porque `/cuentas` y el panel preguntaban cuenta por cuenta: nueve
    cuentas eran 39 consultas por página, y cien eran 403.
    """
    # El filtro de fecha va en el ON y no en el WHERE: en un LEFT JOIN, un
    # WHERE sobre la tabla de la derecha se carga las cuentas sin movimientos.
    corte = "AND t.date <= ?" if as_of else ""
    saldos = {
        r["id"]: round(r["bal"] if r["bal"] is not None else 0, 2)
        for r in cur.execute(
            f"""SELECT a.id, a.initial_balance + COALESCE(SUM(t.amount), 0) AS bal
                FROM accounts a
                LEFT JOIN transactions t ON t.account_id = a.id {corte}
                GROUP BY a.id""",
            (as_of,) if as_of else (),
        )
    }
    # La última valoración de cada cuenta de inversión, de una vez. El
    # desempate —fecha y, a igualdad, id— es el mismo que en last_valuation().
    for r in cur.execute(
        f"""SELECT account_id, value FROM (
                SELECT account_id, value,
                       ROW_NUMBER() OVER (PARTITION BY account_id
                                          ORDER BY date DESC, id DESC) AS n
                FROM account_valuations
                {"WHERE date <= ?" if as_of else ""}
            ) WHERE n = 1""",
        (as_of,) if as_of else (),
    ):
        if r["account_id"] in saldos:
            saldos[r["account_id"]] = round(r["value"], 2)
    return saldos


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
    saldos = balances_by_account(cur, as_of)
    activas = [r["id"] for r in cur.execute(
        "SELECT id FROM accounts WHERE archived = 0")]
    return round(sum(saldos.get(i, 0.0) for i in activas), 2)


def balance_series(cur: sqlite3.Cursor, months: int = 6) -> list[dict]:
    """Saldo acumulado al cierre de cada uno de los últimos N meses con datos.

    La ventana termina en el último mes que tiene datos —un movimiento o una
    valoración—, no en el mes actual del calendario. Si los últimos extractos
    importados son de abril y hoy es septiembre, prolongar la serie hasta hoy
    la rellena de meses arrastrados que expulsan de la ventana justo los que
    varían, y la curva sale recta. Es el mismo criterio con el que el panel
    cae al último mes con datos cuando el mes en curso está vacío.

    Los huecos *dentro* del rango sí se arrastran: un mes sin movimientos
    cierra con el saldo del mes anterior, no con cero.
    """
    # Saldo inicial total
    ib_row = cur.execute(
        "SELECT COALESCE(SUM(initial_balance), 0) AS ib FROM accounts WHERE archived = 0"
    ).fetchone()
    initial = ib_row["ib"] or 0

    # Flujo acumulado por mes. Solo cuentas activas: si el saldo inicial de una
    # archivada no entra en el patrimonio, sus movimientos tampoco pueden mover
    # la curva.
    rows = cur.execute(
        """SELECT substr(date, 1, 7) AS ym, SUM(amount) AS delta
           FROM transactions
           WHERE account_id IN (SELECT id FROM accounts WHERE archived = 0)
           GROUP BY ym ORDER BY ym"""
    ).fetchall()
    delta_by_month = {r["ym"]: r["delta"] for r in rows}
    data_months = {r["ym"] for r in rows}

    # Las cuentas de inversión no siguen la suma de movimientos: su valor lo
    # marca la última valoración declarada. Se restan de la serie acumulada y
    # se suman aparte, mes a mes, con la valoración vigente en cada cierre.
    inv = cur.execute(
        "SELECT id, initial_balance FROM accounts "
        "WHERE archived = 0 AND type = ?", (INVESTMENT_TYPE,),
    ).fetchall()
    inv_ids = [r["id"] for r in inv]
    # Flujo y valoraciones de las cuentas de inversión, dos consultas para
    # todas. Antes el bucle de meses preguntaba una vez por mes y por cuenta:
    # ocho consultas con un solo fondo y ocho meses, y una más por cada mes de
    # histórico que pasara. Aquí se traen enteras y se recorren en memoria.
    inv_flow: dict[int, dict[str, float]] = {i: {} for i in inv_ids}
    inv_vals: dict[int, list[tuple[str, float]]] = {i: [] for i in inv_ids}
    if inv_ids:
        marks = ",".join("?" * len(inv_ids))
        initial -= sum(r["initial_balance"] for r in inv)
        for r in cur.execute(
            f"""SELECT account_id, substr(date, 1, 7) AS ym, SUM(amount) AS delta
                FROM transactions WHERE account_id IN ({marks})
                GROUP BY account_id, ym""", inv_ids,
        ):
            inv_flow[r["account_id"]][r["ym"]] = r["delta"]
            delta_by_month[r["ym"]] = delta_by_month.get(r["ym"], 0) - r["delta"]
        # Una valoración nueva mueve el patrimonio sin ningún movimiento
        # detrás, así que también marca hasta dónde llega la serie.
        for r in cur.execute(
            f"""SELECT account_id, date, value FROM account_valuations
                WHERE account_id IN ({marks})
                ORDER BY account_id, date""", inv_ids,
        ):
            inv_vals[r["account_id"]].append((r["date"], r["value"]))
            data_months.add(r["date"][:7])

    # Construir series
    if not data_months:
        return []
    result = []
    running = initial
    # Vamos mes a mes desde el más antiguo hasta el último con datos
    start_ym, end_ym = min(data_months), max(data_months)

    # Lo aportado a cada fondo, que se va acumulando con los meses, y un
    # puntero a su valoración vigente. Los meses anteriores al arranque de la
    # serie entran ya sumados: no debería haberlos, pero si los hubiera no
    # pueden perderse.
    aportado = {r["id"]: r["initial_balance"] for r in inv}
    for account_id, por_mes in inv_flow.items():
        aportado[account_id] += sum(d for ym, d in por_mes.items() if ym < start_ym)
    vigente = {i: -1 for i in inv_ids}   # -1 = todavía sin valorar

    y, m = int(start_ym[:4]), int(start_ym[5:7])
    while f"{y:04d}-{m:02d}" <= end_ym:
        ym = f"{y:04d}-{m:02d}"
        running += delta_by_month.get(ym, 0)
        total = running
        if inv_ids:
            # Último día del mes, para tomar la valoración vigente entonces
            nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
            month_end = (nxt - timedelta(days=1)).isoformat()
            for account_id in inv_ids:
                aportado[account_id] += inv_flow[account_id].get(ym, 0)
                vals = inv_vals[account_id]
                i = vigente[account_id]
                while i + 1 < len(vals) and vals[i + 1][0] <= month_end:
                    i += 1
                vigente[account_id] = i
                total += vals[i][1] if i >= 0 else round(aportado[account_id], 2)
        result.append({"month": ym, "balance": round(total, 2)})
        m += 1
        if m == 13:
            m = 1
            y += 1
    return result[-months:]
