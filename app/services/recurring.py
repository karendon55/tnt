"""
Detección de gastos recurrentes, duplicados y subidas de precio.
Heurística 100% local.
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, median, pstdev


def _payee_key(description: str) -> str:
    """
    Clave de comercio: toma las 2 primeras palabras significativas en mayúsculas.
    Ej: 'Pago en MERCADONA P DE LAS DELICI MADRID ES' -> 'MERCADONA P'
    """
    up = description.upper()
    for prefix in ("PAGO EN ", "PAGO A ", "COMPRA EN ", "RECIBO "):
        if up.startswith(prefix):
            up = up[len(prefix):]
    tokens = re.findall(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\.]{2,}", up)
    stop = {"ES", "SL", "SA", "SLU", "MADRID", "BARCELONA", "ESPAÑA"}
    keep = [t for t in tokens if t not in stop]
    return " ".join(keep[:2]) if keep else up[:20]


@dataclass
class RecurringGroup:
    payee_key: str
    description_sample: str
    count: int
    avg_amount: float
    median_amount: float
    last_date: str
    # El último movimiento del grupo. Va aquí porque quien avisa de subidas de
    # precio lo necesita, y preguntarlo otra vez a la base era una consulta por
    # grupo —37 en la base real— para un dato que ya estaba calculado.
    last_id: int
    last_amount: float
    avg_interval_days: float
    kind: str   # 'monthly' | 'quarterly' | 'irregular'
    stability: float  # 0..1, cuanto más cerca de 1 más regular


def find_recurring(cur: sqlite3.Cursor, min_occurrences: int = 3) -> list[RecurringGroup]:
    """
    Busca grupos de transacciones con la misma clave de comercio que se
    repiten con intervalo aproximadamente mensual o trimestral.
    """
    rows = cur.execute(
        """SELECT id, account_id, date, amount, description
           FROM transactions
           WHERE transfer_id IS NULL
           ORDER BY date"""
    ).fetchall()

    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        # Separar por signo para que gasto y ingreso no se mezclen
        sign = "+" if r["amount"] >= 0 else "-"
        key = f"{sign}{_payee_key(r['description'])}"
        groups[key].append(r)

    results = []
    for key, items in groups.items():
        if len(items) < min_occurrences:
            continue
        dates = [date.fromisoformat(i["date"]) for i in items]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not intervals:
            continue
        avg_int = mean(intervals)
        std = pstdev(intervals) if len(intervals) > 1 else 0
        stability = max(0.0, 1.0 - (std / avg_int if avg_int > 0 else 1.0))

        if 25 <= avg_int <= 35 and stability >= 0.6:
            kind = "monthly"
        elif 85 <= avg_int <= 95 and stability >= 0.6:
            kind = "quarterly"
        elif stability >= 0.5:
            kind = "irregular"
        else:
            continue

        amounts = [i["amount"] for i in items]
        results.append(RecurringGroup(
            payee_key=key.lstrip("+-"),
            description_sample=items[-1]["description"],
            count=len(items),
            avg_amount=round(mean(amounts), 2),
            median_amount=round(median(amounts), 2),
            last_date=items[-1]["date"],
            last_id=items[-1]["id"],
            last_amount=items[-1]["amount"],
            avg_interval_days=round(avg_int, 1),
            kind=kind,
            stability=round(stability, 2),
        ))

    results.sort(key=lambda g: abs(g.avg_amount), reverse=True)
    return results


# Con menos repeticiones no hay mediana en la que confiar para decir que algo
# ha subido de precio. La previsión se conforma con dos.
MIN_PARA_ANOMALIAS = 3


@dataclass
class Anomaly:
    kind: str                # 'duplicate' | 'price_jump' | 'missing_recurring'
    message: str
    transaction_ids: list[int]
    amount: float | None = None


def detect_anomalies(cur: sqlite3.Cursor,
                     recurrings: list[RecurringGroup] | None = None) -> list[Anomaly]:
    """Duplicados y subidas de precio.

    `recurrings` permite pasarle los grupos ya calculados. Es para el panel,
    que también los necesita para la previsión: buscarlos es leer la tabla de
    movimientos entera y reagruparla, y hacerlo dos veces por página era el 66 %
    del tiempo de la portada. Pueden venir con un mínimo de repeticiones más
    flojo del que se quiere aquí; el mínimo solo filtra, así que se filtra."""
    anomalies: list[Anomaly] = []

    # 1. Duplicados en ventana de 3 días: mismo importe, cuenta y descripción.
    # Si ambas traen saldo y son diferentes, son movs reales y legítimos (p.ej.
    # dos recargas de 30€ el mismo día). Filtramos esos falsos positivos.
    dup_rows = cur.execute(
        """SELECT t1.id AS a_id, t2.id AS b_id, t1.amount, t1.description, t1.date,
                  t1.balance AS bal1, t2.balance AS bal2
           FROM transactions t1 JOIN transactions t2 ON
               t1.account_id = t2.account_id
               AND t1.amount = t2.amount
               AND t1.description = t2.description
               AND t1.id < t2.id
               AND ABS(julianday(t1.date) - julianday(t2.date)) <= 3
               AND t1.transfer_id IS NULL"""
    ).fetchall()
    for d in dup_rows:
        if (d["bal1"] is not None and d["bal2"] is not None
                and abs(d["bal1"] - d["bal2"]) > 0.01):
            # Saldos distintos ⇒ son dos movs reales, no duplicado
            continue
        anomalies.append(Anomaly(
            kind="duplicate",
            message=f"Posible duplicado: {d['description']} · {abs(d['amount']):.2f} €",
            transaction_ids=[d["a_id"], d["b_id"]],
            amount=d["amount"],
        ))

    # 2. Subidas de precio en recurrentes.
    # El último movimiento sale del propio grupo. Antes se preguntaba a la base
    # por descripción, una consulta por grupo, y además sin excluir traspasos:
    # un movimiento espejo con la misma descripción se colaba como si fuera la
    # última factura y saltaba un aviso de subida que no existía.
    if recurrings is None:
        recurrings = find_recurring(cur, min_occurrences=MIN_PARA_ANOMALIAS)
    for g in recurrings:
        if g.count < MIN_PARA_ANOMALIAS:
            continue
        prev_median = g.median_amount
        if abs(prev_median) < 1:
            continue
        # Subida de precio: era gasto (negativo) y se volvió más negativo >15%
        if prev_median < 0 and g.last_amount < 0 and abs(g.last_amount) > abs(prev_median) * 1.15:
            anomalies.append(Anomaly(
                kind="price_jump",
                message=f"«{g.payee_key}» subió de {abs(prev_median):.2f}€ a {abs(g.last_amount):.2f}€",
                transaction_ids=[g.last_id],
                amount=g.last_amount,
            ))

    return anomalies
