"""
Router /movimientos — lista paginada con filtros y recategorización inline.
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.db import cursor
from app.services.analytics import category_tree
from app.services.categorizer import extract_tokens
from app.templating import templates
from app.utils.forms import to_int_or_none

router = APIRouter()

PAGE_SIZE = 50


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
        where.append("(LOWER(t.description) LIKE ? OR LOWER(COALESCE(t.memo, '')) LIKE ?)")
        params.append(f"%{q.lower()}%")
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
    account_id_i = to_int_or_none(account_id)
    category_id_i = to_int_or_none(category_id)
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
        cat_tree = category_tree(cur)  # árbol de categorías para el selector

        total = cur.execute(
            f"""SELECT COUNT(*) AS n
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                {clause}""",
            params,
        ).fetchone()["n"]

        rows = cur.execute(
            f"""SELECT t.id, t.date, t.amount, t.description, t.memo, t.transfer_id,
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

    txs = [
        {
            "id": r["id"], "date": r["date"], "amount": r["amount"],
            "description": r["description"],
            "memo": r["memo"] or "",
            "account_name": r["account_name"],
            "is_transfer": r["transfer_id"] is not None,
            "auto": bool(r["auto_categorized"]),
            "cat_id": r["cat_id"],
            # "Categoría" = la padre si la asignada tiene padre, si no la propia.
            # "Subcategoría" = la propia sólo cuando tiene padre.
            "category_label": r["parent_name"] or r["cat_name"] or "Sin categoría",
            "subcategory_label": r["cat_name"] if r["parent_name"] else "",
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
    """Cambia la categoría de un movimiento y (si procede) sugiere una regla.

    Tras asignar categoría, buscamos tokens distintivos de la descripción y
    miramos cuántos *otros* movimientos del usuario los comparten. Si hay
    al menos 1 más, devolvemos junto con la celda una propuesta de regla.
    """
    with cursor() as cur:
        tx_row = cur.execute(
            "SELECT description FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        description = tx_row["description"] if tx_row else ""

        if category_id == "" or category_id == "null":
            cur.execute(
                "UPDATE transactions SET category_id = NULL, auto_categorized = 0, "
                "confidence = NULL WHERE id = ?",
                (tx_id,),
            )
            label = "Sin categoría"
            sub_label = ""
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
            sub_label = row["n"] if (row and row["pn"]) else ""

        cat_tree = category_tree(cur)  # árbol de categorías para el selector

        # Sugerir una regla sólo si hemos asignado categoría real (no limpiado).
        suggestion = None
        if cat_id_int is not None and description:
            suggestion = _best_rule_suggestion(cur, description, cat_id_int)

    return templates.TemplateResponse(
        request, "_category_cell.html",
        {
            "tx": {
                "id": tx_id, "cat_id": cat_id_int,
                "category_label": label, "subcategory_label": sub_label,
            },
            "cat_tree": cat_tree,
            "suggestion": suggestion,
            "oob_subcat": True,  # incluye el OOB swap para la celda hermana
        },
    )


def _best_rule_suggestion(
    cur, description: str, category_id: int
) -> Optional[dict]:
    """Devuelve el mejor token candidato a regla, o None si no merece sugerir.

    Criterio: el token debe aparecer en ≥1 movimiento *sin* categoría o con
    otra categoría distinta, y NO debe existir ya una regla activa con ese
    mismo patrón apuntando a esta misma categoría.
    """
    tokens = extract_tokens(description)
    if not tokens:
        return None

    best = None
    for tok in tokens:
        # ¿Hay ya una regla igual?
        exists = cur.execute(
            "SELECT 1 FROM category_rules WHERE pattern = ? AND category_id = ?",
            (tok, category_id),
        ).fetchone()
        if exists:
            continue

        # Cuántos otros movimientos tienen este token Y no tienen ya esta categoría.
        # Usamos LIKE sobre UPPER(description) porque extract_tokens devuelve mayúsculas.
        n = cur.execute(
            """SELECT COUNT(*) AS n
               FROM transactions
               WHERE UPPER(description) LIKE ?
                 AND (category_id IS NULL OR category_id != ?)""",
            (f"%{tok}%", category_id),
        ).fetchone()["n"]
        if n < 1:
            continue

        if best is None or n > best["matches"]:
            best = {"token": tok, "matches": n, "category_id": category_id}
    return best


@router.post("/movimientos/{tx_id}/memo", response_class=HTMLResponse)
def update_memo(request: Request, tx_id: int, memo: str = Form("")):
    """Guarda el memo manual de una transacción. Vacío => NULL."""
    clean = (memo or "").strip()
    with cursor() as cur:
        cur.execute(
            "UPDATE transactions SET memo = ? WHERE id = ?",
            (clean or None, tx_id),
        )
    return templates.TemplateResponse(
        request, "_memo_cell.html",
        {"tx": {"id": tx_id, "memo": clean}},
    )


def _manual_hash(account_id: int, tx_date: str, amount: float, description: str) -> str:
    """Hash estable para movimientos manuales. Prefijo 'manual:' evita colisión
    con los importados. Incluye un timestamp para permitir varios idénticos el
    mismo día (caso típico: dos cafés a 2 €)."""
    ts = datetime.now().isoformat()
    blob = f"manual|{account_id}|{tx_date}|{amount:.2f}|{description.strip().lower()}|{ts}"
    return "manual:" + hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _unlink_transfer_pair(cur, tx_id: int) -> None:
    """Si el movimiento estaba enlazado como traspaso, rompe el vínculo en
    ambos extremos. Se invoca antes de editar importe/fecha/cuenta o borrar."""
    row = cur.execute(
        "SELECT transfer_id FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if row and row["transfer_id"]:
        pair = row["transfer_id"]
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (tx_id,))
        cur.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (pair,))


@router.post("/movimientos/nuevo")
def transaction_create(
    request: Request,
    account_id: int = Form(...),
    date: str = Form(...),                      # noqa: A002 — shadow builtin, OK en handler
    amount: float = Form(...),
    description: str = Form(...),
    memo: str = Form(""),
    category_id: str = Form(""),
):
    """Crea un movimiento manual (gasto en efectivo, corrección, etc.)."""
    desc = (description or "").strip() or "(manual)"
    cat_id = to_int_or_none(category_id)
    with cursor() as cur:
        cur.execute(
            """INSERT INTO transactions(
                account_id, date, amount, description, memo,
                category_id, auto_categorized, confidence,
                transfer_id, payee, balance, source_hint, hash
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL, 'manual', ?)""",
            (
                account_id, date, amount, desc, (memo or "").strip() or None,
                cat_id, 1.0 if cat_id else None,
                _manual_hash(account_id, date, amount, desc),
            ),
        )
    return RedirectResponse("/movimientos", status_code=303)


@router.post("/movimientos/{tx_id}/editar")
def transaction_update(
    tx_id: int,
    account_id: int = Form(...),
    date: str = Form(...),                      # noqa: A002
    amount: float = Form(...),
    description: str = Form(...),
    memo: str = Form(""),
    category_id: str = Form(""),
):
    """Edita un movimiento existente. Si cambiaron campos clave (importe, fecha,
    cuenta), se rompe el enlace de traspaso por si ya no es simétrico."""
    desc = (description or "").strip() or "(manual)"
    cat_id = to_int_or_none(category_id)
    with cursor() as cur:
        old = cur.execute(
            "SELECT account_id, date, amount FROM transactions WHERE id = ?", (tx_id,)
        ).fetchone()
        if not old:
            return RedirectResponse("/movimientos", status_code=303)

        key_changed = (
            old["account_id"] != account_id
            or old["date"] != date
            or round(old["amount"], 2) != round(amount, 2)
        )
        if key_changed:
            _unlink_transfer_pair(cur, tx_id)

        cur.execute(
            """UPDATE transactions SET
                account_id = ?, date = ?, amount = ?,
                description = ?, memo = ?, category_id = ?,
                auto_categorized = CASE WHEN ? IS NULL THEN 0 ELSE auto_categorized END,
                confidence = CASE WHEN ? IS NULL THEN NULL ELSE confidence END,
                balance = NULL
               WHERE id = ?""",
            (
                account_id, date, amount, desc,
                (memo or "").strip() or None, cat_id,
                cat_id, cat_id, tx_id,
            ),
        )
    return RedirectResponse("/movimientos", status_code=303)


@router.post("/movimientos/{tx_id}/borrar")
def transaction_delete(tx_id: int):
    """Borra un movimiento. Si estaba enlazado como traspaso, desenlaza antes."""
    with cursor() as cur:
        _unlink_transfer_pair(cur, tx_id)
        cur.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return RedirectResponse("/movimientos", status_code=303)


@router.get("/exportar.csv")
def export_csv(
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
):
    clause, params = _build_query(
        to_int_or_none(account_id),
        to_int_or_none(category_id),
        date_from or None,
        date_to or None,
        (q or "").strip() or None,
    )
    with cursor() as cur:
        rows = cur.execute(
            f"""SELECT t.date, a.name AS account, t.description, t.memo, t.amount,
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
    writer.writerow(["Fecha", "Cuenta", "Descripción", "Memo", "Importe", "Categoría", "Saldo"])
    for r in rows:
        writer.writerow([
            r["date"], r["account"], r["description"],
            r["memo"] or "",
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
