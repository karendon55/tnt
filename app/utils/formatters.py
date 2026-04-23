"""
Formateadores de números en estilo español (es-ES).

Convención: miles con punto, decimales con coma. Ej: 197836.15 → "197.836,15".

Se exponen como filtros Jinja en `app/templating.py`:
    {{ value | eur }}         →  "197.836,15 €"
    {{ value | eur_signed }}  →  "+197.836,15 €"  (siempre incluye signo)
    {{ value | pct_signed }}  →  "+1,5%"
    {{ value | num_es }}      →  "197.836,15"      (sin €)

Todos aceptan None y devuelven cadena vacía en ese caso.
"""
from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_abs(value: float, decimals: int) -> str:
    """Formatea |value| como cadena es-ES (miles con '.', decimales con ',')."""
    # Python usa en-US por defecto: 197,836.15
    s = f"{abs(value):,.{decimals}f}"
    # Swap: , → . (miles), . → , (decimales). Usamos un carácter intermedio.
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def num_es(value: Any, decimals: int = 2) -> str:
    """Número en estilo español, sin unidad. Negativos con '-' delante."""
    v = _to_float(value)
    if v is None:
        return ""
    sign = "-" if v < 0 else ""
    return f"{sign}{_fmt_abs(v, decimals)}"


def eur(value: Any, decimals: int = 2) -> str:
    """Importe en euros sin forzar signo. Ej: 197836.15 → '197.836,15 €'."""
    v = _to_float(value)
    if v is None:
        return ""
    sign = "-" if v < 0 else ""
    return f"{sign}{_fmt_abs(v, decimals)} €"


def eur_signed(value: Any, decimals: int = 2) -> str:
    """Importe en euros siempre con signo explícito. Ej: 62.50 → '+62,50 €'."""
    v = _to_float(value)
    if v is None:
        return ""
    sign = "+" if v >= 0 else "-"
    return f"{sign}{_fmt_abs(v, decimals)} €"


def pct_signed(value: Any, decimals: int = 1) -> str:
    """Porcentaje siempre con signo. Ej: -1.5 → '-1,5%'."""
    v = _to_float(value)
    if v is None:
        return ""
    sign = "+" if v >= 0 else "-"
    return f"{sign}{_fmt_abs(v, decimals)}%"
