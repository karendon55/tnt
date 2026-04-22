"""
Router /presupuestos — límite mensual por categoría con barra de progreso.
Cuando un presupuesto supera el 100% aparece la pill Highway to Hell. 🔥
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services.analytics import month_label, month_range
from app.templating import templates

router = APIRouter()


def _load_budgets(cur, start: str, end: str) -> list[dict]:
    rows = cur.execute(
        """SELECT b.id, b.category_id, b.monthly_limit, b.active,
                  c.name AS cat_name, c.kind, c.parent_id,
                  pc.name AS parent_name
           FROM budgets b
           JOIN categories c ON c.id = b.category_id
           LEFT JOIN categories pc ON pc.id = c.parent_id
           WHERE b.active = 1
           ORDER BY c.name"""
    ).fetchall()

    items = []
    for r in rows:
        spent_row = cur.execute(
            """SELECT COALESCE(SUM(-t.amount), 0) AS spent
               FROM transactions t
               LEFT JOIN categories c ON c.id = t.category_id
               WHERE t.date BETWEEN ? AND ?
                 AND t.amount < 0
                 AND t.transfer_id IS NULL
                 AND (t.category_id = ? OR c.parent_id = ?)""",
            (start, end, r["category_id"], r["category_id"]),
        ).fetchone()
        spent = round(spent_row["spent"] or 0, 2)
        limit = r["monthly_limit"]
        pct = round(spent / limit * 100, 1) if limit > 0 else 0
        items.append({
            "id": r["id"], "category_id": r["category_id"],
            "name": r["cat_name"],
            "display_name": r["parent_name"] + " · " + r["cat_name"] if r["parent_name"] else r["cat_name"],
            "limit": limit,
            "spent": spent,
            "remaining": round(limit - spent, 2),
            "pct": pct,
            "over": pct > 100,
            "warn": 80 <= pct <= 100,
        })
    items.sort(key=lambda i: i["pct"], reverse=True)
    return items


@router.get("/presupuestos", response_class=HTMLResponse)
def budgets_list(request: Request):
    with cursor() as cur:
        cur_ym = date.today().strftime("%Y-%m")
        has_current = cur.execute(
            "SELECT 1 FROM transactions WHERE substr(date,1,7) = ? LIMIT 1",
            (cur_ym,),
        ).fetchone() is not None
        if has_current:
            m_start, m_end = month_range()
            showing_latest = False
        else:
            latest = cur.execute(
                "SELECT MAX(substr(date,1,7)) AS ym FROM transactions"
            ).fetchone()["ym"]
            if latest:
                y, m = int(latest[:4]), int(latest[5:7])
                m_start, m_end = month_range(date(y, m, 1))
                showing_latest = True
            else:
                m_start, m_end = month_range()
                showing_latest = False

        items = _load_budgets(cur, m_start, m_end)
        all_cats = cur.execute(
            """SELECT c.id, c.name, c.parent_id, pc.name AS parent_name
               FROM categories c
               LEFT JOIN categories pc ON pc.id = c.parent_id
               WHERE c.kind = 'expense'
                 AND c.id NOT IN (SELECT category_id FROM budgets WHERE active = 1)
               ORDER BY c.parent_id IS NOT NULL, c.name"""
        ).fetchall()
        pickable = [
            {
                "id": c["id"],
                "label": (c["parent_name"] + " · " + c["name"]) if c["parent_name"] else c["name"],
                "is_sub": c["parent_id"] is not None,
            }
            for c in all_cats
        ]

    total_limit = sum(i["limit"] for i in items)
    total_spent = sum(i["spent"] for i in items)
    total_pct = round(total_spent / total_limit * 100, 1) if total_limit > 0 else 0

    return templates.TemplateResponse(
        request, "budgets.html",
        {
            "active": "budgets",
            "budgets": items,
            "pickable": pickable,
            "month_name": month_label(m_start[:7]),
            "showing_latest": showing_latest,
            "totals": {
                "limit": total_limit, "spent": total_spent, "pct": total_pct,
                "over": total_pct > 100,
            },
        },
    )


@router.post("/presupuestos/nuevo")
def budgets_create(
    category_id: int = Form(...),
    monthly_limit: float = Form(...),
):
    with cursor() as cur:
        cur.execute(
            "INSERT INTO budgets(category_id, monthly_limit, active) VALUES (?, ?, 1) "
            "ON CONFLICT(category_id) DO UPDATE SET monthly_limit = excluded.monthly_limit, active = 1",
            (category_id, monthly_limit),
        )
    return RedirectResponse("/presupuestos", status_code=303)


@router.post("/presupuestos/{budget_id}/editar")
def budgets_update(budget_id: int, monthly_limit: float = Form(...)):
    with cursor() as cur:
        cur.execute(
            "UPDATE budgets SET monthly_limit = ? WHERE id = ?",
            (monthly_limit, budget_id),
        )
    return RedirectResponse("/presupuestos", status_code=303)


@router.post("/presupuestos/{budget_id}/borrar")
def budgets_delete(budget_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    return RedirectResponse("/presupuestos", status_code=303)
