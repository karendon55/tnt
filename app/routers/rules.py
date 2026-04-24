"""
Router /reglas — gestión de reglas de categorización automática.

Dos orígenes de reglas en BD:
- `builtin`: sembradas por `categorizer.seed_builtin_rules` (MERCADONA, IBERDROLA…).
- `learned`: extraídas automáticamente de movimientos ya categorizados.
- `manual`: creadas desde la UI tras recategorizar un movimiento (prioridad alta).

Una regla aplicada retroactivamente sólo toca movimientos SIN categoría (para
no pisar decisiones manuales del usuario).
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.templating import templates

router = APIRouter()


@router.get("/reglas", response_class=HTMLResponse)
def rules_list(request: Request):
    with cursor() as cur:
        rows = cur.execute(
            """SELECT r.id, r.pattern, r.category_id, r.priority, r.source, r.hits,
                      c.name AS cat_name, pc.name AS parent_name
               FROM category_rules r
               LEFT JOIN categories c  ON c.id  = r.category_id
               LEFT JOIN categories pc ON pc.id = c.parent_id
               ORDER BY r.source, r.pattern"""
        ).fetchall()

        cats = cur.execute(
            "SELECT id, name, parent_id FROM categories "
            "ORDER BY parent_id IS NOT NULL, name"
        ).fetchall()

    rules = []
    for r in rows:
        label = r["parent_name"] + " · " + r["cat_name"] if r["parent_name"] else (r["cat_name"] or "—")
        rules.append({
            "id": r["id"], "pattern": r["pattern"], "source": r["source"],
            "priority": r["priority"], "hits": r["hits"],
            "category_id": r["category_id"], "category_label": label,
        })

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

    return templates.TemplateResponse(
        request, "rules.html",
        {"active": "rules", "rules": rules, "cat_tree": cat_tree},
    )


@router.post("/reglas/crear", response_class=HTMLResponse)
def rule_create(
    request: Request,
    pattern: str = Form(...),
    category_id: int = Form(...),
    tx_id: int = Form(None),  # opcional: viene si la creas desde la sugerencia inline
):
    """Crea regla manual y la aplica retroactivamente a movimientos sin categoría.

    Si `tx_id` viene, respondemos con un HTML pequeño (confirmación inline vía
    HTMX). Si no, redirigimos a /reglas.
    """
    clean = (pattern or "").strip().upper()
    if not clean:
        if tx_id is not None:
            return HTMLResponse("")
        return RedirectResponse("/reglas", status_code=303)

    with cursor() as cur:
        existing = cur.execute(
            "SELECT id FROM category_rules WHERE pattern = ? AND category_id = ?",
            (clean, category_id),
        ).fetchone()
        if existing:
            rule_id = existing["id"]
        else:
            cur.execute(
                """INSERT INTO category_rules(pattern, category_id, priority, source, hits)
                   VALUES (?, ?, ?, 'manual', 1)""",
                (clean, category_id, 200),  # prioridad alta: gana a builtin
            )
            rule_id = cur.lastrowid

        # Aplicar retroactivamente sólo a los NO categorizados.
        applied = cur.execute(
            """UPDATE transactions
               SET category_id = ?, auto_categorized = 1, confidence = 0.9
               WHERE category_id IS NULL
                 AND UPPER(description) LIKE ?""",
            (category_id, f"%{clean}%"),
        ).rowcount

        # Actualizar hits
        cur.execute(
            "UPDATE category_rules SET hits = hits + ? WHERE id = ?",
            (applied, rule_id),
        )

    if tx_id is not None:
        return templates.TemplateResponse(
            request, "_rule_created.html",
            {"token": clean, "applied": applied, "tx_id": tx_id},
        )
    return RedirectResponse("/reglas", status_code=303)


@router.post("/reglas/{rule_id}/borrar")
def rule_delete(rule_id: int):
    """Borra una regla. No re-categoriza retroactivamente: los movimientos
    que ya tenían esa categoría la conservan."""
    with cursor() as cur:
        cur.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
    return RedirectResponse("/reglas", status_code=303)


@router.post("/reglas/{rule_id}/editar")
def rule_update(
    rule_id: int,
    pattern: str = Form(...),
    category_id: int = Form(...),
    priority: int = Form(100),
):
    with cursor() as cur:
        cur.execute(
            """UPDATE category_rules
               SET pattern = ?, category_id = ?, priority = ?
               WHERE id = ?""",
            (pattern.strip().upper(), category_id, priority, rule_id),
        )
    return RedirectResponse("/reglas", status_code=303)


@router.post("/reglas/reentrenar")
def rules_retrain():
    """Relanza aprendizaje desde los movimientos ya categorizados + aplica reglas
    a los no categorizados. Útil tras una temporada de recategorización manual."""
    from app.services.categorizer import retrain_and_apply
    with cursor() as cur:
        retrain_and_apply(cur)
    return RedirectResponse("/reglas", status_code=303)
