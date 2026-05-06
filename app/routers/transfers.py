"""
Router /traspasos — emparejamiento manual de transferencias entre cuentas.

Cuando dos movimientos en cuentas distintas son los dos lados de un mismo
traspaso (importes opuestos, fecha cercana), TNT los empareja por
`transfer_id`. La importación automática los detecta en muchos casos, pero
no siempre: aquí permitimos:

  · Ver los pares ya emparejados.
  · Romper un emparejamiento incorrecto.
  · Emparejar a mano dos movimientos sueltos.
  · Aceptar de un click sugerencias evidentes (mismo importe absoluto,
    cuentas distintas, fechas a ±3 días).
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.templating import templates

router = APIRouter()


def _unlink_pair(cur, tx_id: int) -> None:
    row = cur.execute(
        "SELECT transfer_id FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if row and row["transfer_id"]:
        pair = row["transfer_id"]
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (tx_id,))
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (pair,))


def _link_pair(cur, left_id: int, right_id: int) -> tuple[bool, str]:
    """Empareja dos movimientos como traspaso. Devuelve (ok, mensaje)."""
    if left_id == right_id:
        return False, "No puedes emparejar un movimiento consigo mismo."
    rows = cur.execute(
        """SELECT id, account_id, amount, date, transfer_id
           FROM transactions WHERE id IN (?, ?)""",
        (left_id, right_id),
    ).fetchall()
    if len(rows) != 2:
        return False, "No se encontraron los dos movimientos."
    a, b = rows[0], rows[1]
    if a["transfer_id"] or b["transfer_id"]:
        return False, "Alguno ya está emparejado. Desemparéjalo primero."
    if a["account_id"] == b["account_id"]:
        return False, "Los dos movimientos son de la misma cuenta."
    if round(a["amount"] + b["amount"], 2) != 0:
        return False, "Los importes no son opuestos (no suman 0)."
    cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (b["id"], a["id"]))
    cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (a["id"], b["id"]))
    return True, "Emparejados correctamente."


@router.get("/traspasos", response_class=HTMLResponse)
def transfers_page(request: Request, msg: str = "", err: str = ""):
    with cursor() as cur:
        # Pares actualmente emparejados. Cada par sale en dos filas; deduplicamos
        # quedándonos con la fila cuyo id < transfer_id (la "izquierda").
        pair_rows = cur.execute(
            """SELECT t1.id  AS left_id,  t1.date AS left_date,
                      t1.amount AS left_amount,
                      t1.description AS left_desc,
                      a1.name AS left_account,
                      t2.id  AS right_id, t2.date AS right_date,
                      t2.amount AS right_amount,
                      t2.description AS right_desc,
                      a2.name AS right_account
               FROM transactions t1
               JOIN transactions t2 ON t2.id = t1.transfer_id
               JOIN accounts a1 ON a1.id = t1.account_id
               JOIN accounts a2 ON a2.id = t2.account_id
               WHERE t1.transfer_id IS NOT NULL
                 AND t1.id < t2.id
               ORDER BY t1.date DESC, t1.id DESC
               LIMIT 200"""
        ).fetchall()
        pairs = [dict(r) for r in pair_rows]

        # Sugerencias automáticas: movs sin emparejar con contrapartida obvia.
        # Mismo |importe|, cuentas distintas, fecha a ±3 días, ambos sin
        # emparejar todavía. Limitamos a 50 pares razonables.
        suggestion_rows = cur.execute(
            """SELECT t1.id  AS left_id,  t1.date AS left_date,
                      t1.amount AS left_amount,
                      t1.description AS left_desc,
                      a1.name AS left_account,
                      t2.id  AS right_id, t2.date AS right_date,
                      t2.amount AS right_amount,
                      t2.description AS right_desc,
                      a2.name AS right_account,
                      ABS(julianday(t1.date) - julianday(t2.date)) AS dist
               FROM transactions t1
               JOIN transactions t2
                 ON t2.account_id != t1.account_id
                AND ROUND(t2.amount + t1.amount, 2) = 0
                AND ABS(julianday(t1.date) - julianday(t2.date)) <= 3
               JOIN accounts a1 ON a1.id = t1.account_id
               JOIN accounts a2 ON a2.id = t2.account_id
               WHERE t1.transfer_id IS NULL
                 AND t2.transfer_id IS NULL
                 AND t1.amount < 0
                 AND t1.id < t2.id
               ORDER BY dist ASC, t1.date DESC
               LIMIT 50"""
        ).fetchall()
        suggestions = [dict(r) for r in suggestion_rows]

        # Movs sueltos para los selectores manuales (últimos 200).
        unlinked_rows = cur.execute(
            """SELECT t.id, t.date, t.amount, t.description, a.name AS account_name
               FROM transactions t JOIN accounts a ON a.id = t.account_id
               WHERE t.transfer_id IS NULL
               ORDER BY t.date DESC, t.id DESC
               LIMIT 200"""
        ).fetchall()
        unlinked = [dict(r) for r in unlinked_rows]

    return templates.TemplateResponse(
        request, "transfers.html",
        {
            "active": "transfers",
            "pairs": pairs,
            "suggestions": suggestions,
            "unlinked": unlinked,
            "msg": msg,
            "err": err,
        },
    )


@router.post("/traspasos/{tx_id}/desemparejar")
def transfers_unlink(tx_id: int):
    with cursor() as cur:
        _unlink_pair(cur, tx_id)
    return RedirectResponse("/traspasos?msg=Par+desemparejado", status_code=303)


@router.post("/traspasos/emparejar")
def transfers_link(left_id: int = Form(...), right_id: int = Form(...)):
    with cursor() as cur:
        ok, message = _link_pair(cur, left_id, right_id)
    qs = ("msg=" if ok else "err=") + message.replace(" ", "+")
    return RedirectResponse(f"/traspasos?{qs}", status_code=303)
