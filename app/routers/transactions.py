"""
Router /movimientos — lista paginada con filtros y recategorización inline.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.db import cursor
from app.templating import templates

router = APIRouter()

PAGE_SIZE = 50


def _to_int_or_none(value: Optional[str]) -> Optional[int]:
    """Convierte '' o None a None, números a int. Silenciosa ante basura."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_query(
    account_id: Optional[int],
    category_id: Optional[int],
    date_from: Optional[str],
    date_to: Optional[str],
    q: Optional[str],
) -> tuple[str, list]:
    where = []
    params: list = []
    if account_id:
        where.append("t.account_id = ?")
        params.append(account_id)
    if category_id == -1:
        where.append("t.category_id IS NULL")
    elif category_id:
        where.append("(c.id = ? OR c.parent_id = ?)")
        params.extend([category_id, category_id])
    if date_from:
        where.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        where.append("t.date <= ?")
        params.append(date_to)
    if q:
        where.append("LOWER(t.description) LIKE ?")
        params.append(f"%{q.lower()}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return clause, params


@router.get("/movimientos", response_class=HTMLResponse)
def transactions_list(
    request: Request,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
):
    account_id_i = _to_int_or_none(account_id)
    category_id_i = _to_int_or_none(category_id)
    date_from = date_from or None
    date_to = date_to or None
    q = (q or "").strip() or None

    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    clause, params = _build_query(account_id_i, category_id_i, date_from, date_to, q)

    with cursor() as cur:
        accounts = cur.execute(
            "SELECT id, name, bank FROM accounts WHERE archived = 0 ORDER BY name"
        ).fetchall()
        cats = cur.execute(
            "SELECT id, name, parent_id FROM categories ORDER BY parent_id IS NOT NULL, name"
        ).fetchall()

        total = cur.execute(
            f"""SELECT COUNT(*) AS n
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                {clause}""",
            params,
        ).fetchone()["n"]

        rows = cur.execute(
            f"""SELECT t.id, t.date, t.amount, t.description, t.transfer_id,
                       t.auto_categorized, a.name AS account_name,
                       c.id AS cat_id, c.name AS cat_name,
                       pc.id AS parent_id, pc.name AS parent_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                LEFT JOIN categories c ON c.id = t.category_id
                LEFT JOIN categories pc ON pc.id = c.parent_id
                {clause}
                ORDER BY t.date DESC, t.id DESC
                LIMIT ? OFFSET ?""",
            params + [PAGE_SIZE, offset],
        ).fetchall()

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # Árbol de categorías para el selector
    cat_tree = []
    by_parent: dict = {}
    for c in cats:
        by_parent.setdefault(c["parent_id"], []).append(c)
    for parent in by_parent.get(None, []):
        cat_tree.append({
            "id": parent["id"], "name": parent["name"],
            "children": [{"id": c["id"], "name": c["name"]}
                         for c in by_parent.get(parent["id"], [])]
        })

    txs = [
        {
            "id": r["id"], "date": r["date"], "amount": r["amount"],
            "description": r["description"],
            "account_name": r["account_name"],
            "is_transfer": r["transfer_id"] is not None,
            "auto": bool(r["auto_categorized"]),
            "cat_id": r["cat_id"],
            "category_label": r["parent_name"] or r["cat_name"] or "Sin categoría",
        }
        for r in rows
    ]

    return templates.TemplateResponse(
        request, "transactions.html",
        {
            "active": "transactions",
            "transactions": txs,
            "accounts": accounts,
            "cat_tree": cat_tree,
            "filters": {
                "account_id": account_id_i, "category_id": category_id_i,
                "date_from": date_from or "", "date_to": date_to or "",
                "q": q or "",
            },
            "page": page, "pages": pages, "total": total,
            "page_size": PAGE_SIZE,
        },
    )


@router.post("/movimientos/{tx_id}/categoria", response_class=HTMLResponse)
def recategorize(request: Request, tx_id: int, category_id: str = Form(...)):
    with cursor() as cur:
        if category_id == "" or category_id == "null":
            cur.execute(
                "UPDATE transactions SET category_id = NULL, auto_categorized = 0, "
                "confidence = NULL WHERE id = ?",
                (tx_id,),
            )
            label = "Sin categoría"
            cat_id_int: Optional[int] = None
        else:
            cat_id_int = int(category_id)
            cur.execute(
                "UPDATE transactions SET category_id = ?, auto_categorized = 0, "
                "confidence = 1.0 WHERE id = ?",
                (cat_id_int, tx_id),
            )
            row = cur.execute(
                """SELECT c.name AS n, pc.name AS pn
                   FROM categories c LEFT JOIN categories pc ON pc.id = c.parent_id
                   WHERE c.id = ?""",
                (cat_id_int,),
            ).fetchone()
            label = (row["pn"] or row["n"]) if row else "Sin categoría"

        cats = cur.execute(
            "SELECT id, name, parent_id FROM categories ORDER BY parent_id IS NOT NULL, name"
        ).fetchall()

    cat_tree = []
    by_parent: dict = {}
    for c in cats:
        by_parent.setdefault(c["parent_id"], []).append(c)
    for parent in by_parent.get(None, []):
        cat_tree.append({
            "id": parent["id"], "name": parent["name"],
            "children": [{"id": c["id"], "name": c["name"]}
                         for c in by_parent.get(parent["id"], [])]
        })

    return templates.TemplateResponse(
        request, "_category_cell.html",
        {"tx": {"id": tx_id, "cat_id": cat_id_int, "category_label": label},
         "cat_tree": cat_tree},
    )


@router.get("/exportar.csv")
def export_csv(
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
):
    clause, params = _build_query(
        _to_int_or_none(account_id),
        _to_int_or_none(category_id),
        date_from or None,
        date_to or None,
        (q or "").strip() or None,
    )
    with cursor() as cur:
        rows = cur.execute(
            f"""SELECT t.date, a.name AS account, t.description, t.amount,
                       COALESCE(pc.name, c.name) AS category, t.balance
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                LEFT JOIN categories c ON c.id = t.category_id
                LEFT JOIN categories pc ON pc.id = c.parent_id
                {clause}
                ORDER BY t.date DESC, t.id DESC""",
            params,
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Fecha", "Cuenta", "Descripción", "Importe", "Categoría", "Saldo"])
    for r in rows:
        writer.writerow([
            r["date"], r["account"], r["description"],
            f"{r['amount']:.2f}".replace(".", ","),
            r["category"] or "",
            f"{r['balance']:.2f}".replace(".", ",") if r["balance"] is not None else "",
        ])
    buf.seek(0)

    filename = f"tnt-movimientos-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
