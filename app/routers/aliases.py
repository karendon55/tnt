"""
Router /alias — gestión de alias de descripciones.

Los alias son cosméticos: la BD guarda la descripción original que mandó
el banco; el alias solo cambia lo que se muestra al usuario en /movimientos
y en el panel.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services.aliases import invalidate as invalidate_alias_cache
from app.templating import templates

router = APIRouter()


@router.get("/alias", response_class=HTMLResponse)
def aliases_list(request: Request, msg: str = ""):
    with cursor() as cur:
        rows = cur.execute(
            """SELECT a.id, a.pattern, a.alias, a.hits, a.created_at,
                      (SELECT COUNT(*) FROM transactions t
                       WHERE UPPER(t.description) LIKE '%' || a.pattern || '%') AS matches
               FROM description_aliases a
               ORDER BY matches DESC, a.pattern"""
        ).fetchall()
        aliases = [dict(r) for r in rows]
    return templates.TemplateResponse(
        request, "aliases.html",
        {"active": "aliases", "aliases": aliases, "msg": msg},
    )


@router.post("/alias/crear")
def aliases_create(pattern: str = Form(...), alias: str = Form(...)):
    pat = pattern.strip().upper()
    al = alias.strip()
    if not pat or not al:
        return RedirectResponse("/alias", status_code=303)
    with cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO description_aliases(pattern, alias) VALUES (?, ?)",
            (pat, al),
        )
    invalidate_alias_cache()
    return RedirectResponse(
        f"/alias?msg=Alias+%E2%80%9C{al}%E2%80%9D+guardado", status_code=303
    )


@router.post("/alias/{alias_id}/editar")
def aliases_update(alias_id: int, pattern: str = Form(...), alias: str = Form(...)):
    pat = pattern.strip().upper()
    al = alias.strip()
    if not pat or not al:
        return RedirectResponse("/alias", status_code=303)
    with cursor() as cur:
        cur.execute(
            "UPDATE description_aliases SET pattern = ?, alias = ? WHERE id = ?",
            (pat, al, alias_id),
        )
    invalidate_alias_cache()
    return RedirectResponse("/alias?msg=Alias+actualizado", status_code=303)


@router.post("/alias/{alias_id}/borrar")
def aliases_delete(alias_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM description_aliases WHERE id = ?", (alias_id,))
    invalidate_alias_cache()
    return RedirectResponse("/alias?msg=Alias+borrado", status_code=303)
