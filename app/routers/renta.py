"""
Router /renta — la declaración de la Renta, dentro de Configuración.

Lee: los importes los calcula app/services/renta.py a partir de los
movimientos. Lo único que escribe son los ajustes de la revisión y, si se
borró alguna, las categorías del módulo.

Lo que llega de fuera se valida aquí. Un ejercicio que no es un año de cuatro
cifras razonable cae en el de por defecto, como el mes del panel. Unos
ajustes que no caben se rechazan enteros, sin guardar la mitad.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.services import renta
from app.templating import templates

router = APIRouter()

_ANIO_MINIMO = 1990
_MAX_INMUEBLE = 80
_MAX_PALABRA = 40
_MAX_PALABRAS = 20


def _ejercicio(valor: str | None, hoy: date) -> int | None:
    """Un año de cuatro cifras entre 1990 y el que viene; si no, None."""
    texto = (valor or "").strip()
    if not re.fullmatch(r"\d{4}", texto):
        return None
    anio = int(texto)
    return anio if _ANIO_MINIMO <= anio <= hoy.year + 1 else None


def _volver(ejercicio: int | None, *, msg: str = "", err: str = "") -> RedirectResponse:
    """De vuelta a la sección, en el mismo ejercicio. El aviso viaja en la URL,
    así que nunca lleva el nombre del piso: es una dirección."""
    qs = {k: v for k, v in (("ejercicio", ejercicio), ("msg", msg), ("err", err)) if v}
    return RedirectResponse(f"/renta?{urlencode(qs)}" if qs else "/renta", status_code=303)


def _enlaces(categoria_id: int, ejercicio: int) -> dict[str, str]:
    """Movimientos y su exportación ya filtran por categoría (con sus hijas) y
    fechas: la sección enlaza ahí en vez de repetir el listado."""
    consulta = urlencode({"category_id": categoria_id, "date_from": f"{ejercicio}-01-01",
                          "date_to": f"{ejercicio}-12-31"})
    return {"ver": f"/movimientos?{consulta}", "csv": f"/exportar.csv?{consulta}"}


@router.get("/renta", response_class=HTMLResponse)
def renta_page(request: Request, ejercicio: str | None = None, msg: str = "", err: str = ""):
    hoy = date.today()
    anio = _ejercicio(ejercicio, hoy) or renta.ejercicio_por_defecto(hoy)
    with cursor() as cur:
        ajustes = renta.cargar_ajustes(cur)
        anios = renta.ejercicios(cur, hoy)
        informe = renta.informe(cur, anio, ajustes)
    if anio not in anios:
        anios = sorted(set(anios) | {anio}, reverse=True)
    enlaces = {clave: _enlaces(ap.categoria_id, anio)
               for clave, ap in informe.apartados.items() if not ap.falta_categoria}
    return templates.TemplateResponse(
        request, "renta.html",
        {
            "active": "renta",
            "ejercicio": anio,
            "ejercicios": anios,
            "informe": informe,
            "ajustes": ajustes,
            "enlaces": enlaces,
            "seguros": renta.SEGUROS,
            "max_inmueble": _MAX_INMUEBLE,
            "msg": msg,
            "err": err,
        },
    )


@router.post("/renta/ajustes")
def renta_ajustes(inmueble: str = Form(""), ignorar: str = Form(""), ejercicio: str = Form("")):
    anio = _ejercicio(ejercicio, date.today())
    nombre = " ".join(inmueble.split())
    palabras = [p for p in (" ".join(x.split()) for x in ignorar.split(",")) if p]
    if len(nombre) > _MAX_INMUEBLE:
        return _volver(anio, err=f"El nombre del piso no puede pasar de {_MAX_INMUEBLE} caracteres.")
    if len(palabras) > _MAX_PALABRAS:
        return _volver(anio, err=f"Como mucho {_MAX_PALABRAS} palabras a ignorar.")
    if any(len(p) > _MAX_PALABRA for p in palabras):
        return _volver(anio, err=f"Cada palabra a ignorar, como mucho {_MAX_PALABRA} caracteres.")
    with cursor() as cur:
        renta.guardar_ajustes(cur, nombre, palabras)
    return _volver(anio, msg="Ajustes guardados.")


@router.post("/renta/categorias")
def renta_reparar(ejercicio: str = Form("")):
    with cursor() as cur:
        renta.reparar_categorias(cur)
    return _volver(_ejercicio(ejercicio, date.today()), msg="Categorías creadas de nuevo.")
