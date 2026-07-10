"""
Router /categorias — árbol jerárquico con crear, renombrar, mover, archivar.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services.analytics import category_monthly_series, month_label
from app.templating import templates

router = APIRouter()


@router.get("/categorias", response_class=HTMLResponse)
def categories_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            """SELECT c.id, c.name, c.parent_id, c.kind,
                      (SELECT COUNT(*) FROM transactions t WHERE t.category_id = c.id) AS tx_count
               FROM categories c
               ORDER BY c.parent_id IS NOT NULL, c.kind DESC, c.name"""
        ).fetchall()

    by_parent: dict = {}
    for r in rows:
        by_parent.setdefault(r["parent_id"], []).append({
            "id": r["id"], "name": r["name"], "kind": r["kind"],
            "parent_id": r["parent_id"], "tx_count": r["tx_count"],
            "children": [],
        })
    parents = by_parent.get(None, [])
    for p in parents:
        p["children"] = by_parent.get(p["id"], [])
        p["child_tx_count"] = sum(c["tx_count"] for c in p["children"])

    expense_parents = [p for p in parents if p["kind"] == "expense"]
    income_parents = [p for p in parents if p["kind"] == "income"]

    return templates.TemplateResponse(
        request, "categories.html",
        {
            "active": "categories",
            "expense_parents": expense_parents,
            "income_parents": income_parents,
            "all_parents": parents,
        },
    )


@router.post("/categorias/nueva")
def categories_create(
    name: str = Form(...),
    parent_id: str = Form(""),
    kind: str = Form("expense"),
):
    parent = int(parent_id) if parent_id else None
    with cursor() as cur:
        if parent:
            parent_row = cur.execute(
                "SELECT kind FROM categories WHERE id = ?", (parent,)
            ).fetchone()
            if parent_row:
                kind = parent_row["kind"]
        cur.execute(
            "INSERT OR IGNORE INTO categories(name, parent_id, kind) VALUES (?, ?, ?)",
            (name.strip(), parent, kind),
        )
    return RedirectResponse("/categorias", status_code=303)


@router.post("/categorias/{cat_id}/renombrar")
def categories_rename(cat_id: int, name: str = Form(...)):
    with cursor() as cur:
        cur.execute("UPDATE categories SET name = ? WHERE id = ?",
                    (name.strip(), cat_id))
    return RedirectResponse("/categorias", status_code=303)


@router.post("/categorias/{cat_id}/mover")
def categories_move(cat_id: int, parent_id: str = Form("")):
    new_parent = int(parent_id) if parent_id else None
    with cursor() as cur:
        if new_parent == cat_id:
            return RedirectResponse("/categorias", status_code=303)
        # Evitar anidamiento en sub de sub: sólo permitimos un nivel
        if new_parent is not None:
            target = cur.execute(
                "SELECT parent_id FROM categories WHERE id = ?", (new_parent,)
            ).fetchone()
            if target and target["parent_id"] is not None:
                return RedirectResponse("/categorias", status_code=303)
        cur.execute(
            "UPDATE categories SET parent_id = ? WHERE id = ?",
            (new_parent, cat_id),
        )
    return RedirectResponse("/categorias", status_code=303)


_LINE_COLORS = [
    "#e10600", "#ff6b35", "#f7b801", "#4ade80", "#38bdf8",
    "#a78bfa", "#f472b6", "#94a3b8",
]


@router.get("/categorias/evolucion", response_class=HTMLResponse)
def categories_evolution(
    request: Request,
    months: int = 12,
    kind: str = "expense",
    top: int = 6,
):
    """Gráfico de líneas: gasto (o ingreso) mensual por categoría padre."""
    months = max(3, min(months, 36))
    top = max(2, min(top, 10))
    if kind not in ("expense", "income"):
        kind = "expense"

    with cursor() as cur:
        data = category_monthly_series(cur, months=months, kind=kind, top_n=top)

    labels = [month_label(ym) for ym in data["months"]]
    datasets = []
    for i, s in enumerate(data["series"]):
        color = _LINE_COLORS[i % len(_LINE_COLORS)]
        datasets.append({
            "label": s["name"],
            "data": s["values"],
            "borderColor": color,
            "backgroundColor": color + "22",
            "tension": 0.3,
            "pointRadius": 2,
        })
    if data["others"]:
        datasets.append({
            "label": "Otros",
            "data": data["others"],
            "borderColor": "#666",
            "borderDash": [4, 4],
            "backgroundColor": "transparent",
            "tension": 0.3,
            "pointRadius": 2,
        })

    has_data = any(any(v > 0 for v in d["data"]) for d in datasets)

    return templates.TemplateResponse(
        request, "categories_evolution.html",
        {
            "active": "categories",
            "months": months,
            "kind": kind,
            "top": top,
            # Va con |safe dentro de <script>: escapar '<' evita que un
            # nombre de categoría con '</script>' rompa/inyecte en la página.
            "chart_json": json.dumps({"labels": labels, "datasets": datasets}).replace("<", "\\u003c"),
            "has_data": has_data,
        },
    )


@router.post("/categorias/{cat_id}/borrar")
def categories_delete(cat_id: int):
    """Borra si no tiene transacciones ni hijos."""
    with cursor() as cur:
        tx = cur.execute(
            "SELECT COUNT(*) AS n FROM transactions WHERE category_id = ?",
            (cat_id,),
        ).fetchone()["n"]
        kids = cur.execute(
            "SELECT COUNT(*) AS n FROM categories WHERE parent_id = ?",
            (cat_id,),
        ).fetchone()["n"]
        if tx == 0 and kids == 0:
            cur.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    return RedirectResponse("/categorias", status_code=303)
