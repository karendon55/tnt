"""
Router /configuracion — índice de los ajustes.

No tiene lógica propia: es la portada de las secciones que se cambian de vez
en cuando (backup, cuentas, categorías, reglas, importación, alias). Cada una
conserva su URL de siempre; aquí solo se enlazan y se describen, para que no
haga falta recordar dónde estaba cada cosa.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.navigation import SECCIONES_CONFIG
from app.templating import templates

router = APIRouter()

@router.get("/configuracion", response_class=HTMLResponse)
def settings_index(request: Request):
    return templates.TemplateResponse(
        request, "settings.html", {"active": "settings", "secciones": SECCIONES_CONFIG},
    )
