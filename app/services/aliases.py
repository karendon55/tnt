"""
Alias de descripciones. La idea: la BD guarda la descripción tal cual la
manda el banco ("BARCO   COMPRA EN DEMARY  FRUTERIAS S.L.") y el alias
("Demary Fruterías") se aplica al renderizar.

Caché en memoria con TTL corto. Se puede invalidar manualmente al crear
o borrar alias para que el siguiente render use la lista actualizada.
"""
from __future__ import annotations

import time
from typing import Optional

# Lista cacheada de tuplas (pattern_upper, alias). Ordenada por longitud
# descendente para que los patrones más específicos ganen.
_CACHE: Optional[list[tuple[str, str]]] = None
_CACHE_TS: float = 0.0
_TTL = 30.0


def _load() -> list[tuple[str, str]]:
    from app.db import cursor
    with cursor() as cur:
        rows = cur.execute(
            "SELECT pattern, alias FROM description_aliases "
            "ORDER BY length(pattern) DESC, pattern"
        ).fetchall()
    return [(r["pattern"], r["alias"]) for r in rows]


def get_aliases() -> list[tuple[str, str]]:
    global _CACHE, _CACHE_TS
    now = time.time()
    if _CACHE is None or now - _CACHE_TS > _TTL:
        _CACHE = _load()
        _CACHE_TS = now
    return _CACHE


def invalidate() -> None:
    global _CACHE
    _CACHE = None


def apply_alias(description: str | None) -> str:
    """Devuelve el alias que coincide con la descripción, o la descripción
    original si no hay match."""
    if not description:
        return ""
    upper = description.upper()
    for pat, alias in get_aliases():
        if pat in upper:
            return alias
    return description
