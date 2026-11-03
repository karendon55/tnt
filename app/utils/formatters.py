"""
Formateadores de números en estilo español (es-ES).

Convención: miles con punto, decimales con coma. Ej: 197836.15 → "197.836,15".

Se exponen como filtros Jinja en `app/templating.py`:
    {{ value | eur }}         →  "197.836,15 €"
    {{ value | eur_signed }}  →  "+197.836,15 €"  (siempre incluye signo)
    {{ value | pct_signed }}  →  "+1,5%"
    {{ value | num_es }}      →  "197.836,15"      (sin €)
    {{ value | fecha }}       →  "31/08/2026"      (desde ISO)

Todos aceptan None y devuelven cadena vacía en ese caso.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from markupsafe import Markup, escape


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


def eur_cifra(value: Any, signed: bool = False) -> Markup:
    """Importe de una cifra grande: la coma, los céntimos y el «€», aparte, para
    pintarlos en pequeño y en voladita (design-system.md, referencia 3).
    501777.72 → '501.777<span class="cifra-cts">,72 €</span>'. El texto es el de
    `eur` (o `eur_signed`): se lee y se copia igual."""
    texto = eur_signed(value) if signed else eur(value)
    entero, coma, resto = texto.rpartition(",")
    if not coma:
        return Markup(escape(texto))
    return Markup(f'{escape(entero)}<span class="cifra-cts">{escape(coma + resto)}</span>')


def pct_signed(value: Any, decimals: int = 1) -> str:
    """Porcentaje siempre con signo. Ej: -1.5 → '-1,5%'."""
    v = _to_float(value)
    if v is None:
        return ""
    sign = "+" if v >= 0 else "-"
    return f"{sign}{_fmt_abs(v, decimals)}%"


def fecha(value: Any) -> str:
    """Fecha en estilo español: 2026-08-31 → 31/08/2026.

    SQLite guarda las fechas en ISO, que es lo correcto para ordenar y comparar,
    pero no es como se lee un extracto aquí. Este filtro es solo para pintar.

    Si el valor trae hora, se conserva sin segundos (31/08/2026 09:48).
    Lo que no sea una fecha se devuelve tal cual: es preferible ver un valor
    raro en la celda a que desaparezca sin dejar rastro.

    OJO: no usar en el value= de un `<input type="date">`. Ahí el navegador
    solo entiende ISO, y con otro formato el campo aparece vacío.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    texto = str(value).strip()
    cabeza, _, cola = texto.partition("T") if "T" in texto else texto.partition(" ")
    try:
        d = date.fromisoformat(cabeza)
    except ValueError:
        return texto
    if cola:
        # La hora puede venir como 09:48 o 09:48:47; nos quedamos con hh:mm.
        hhmm = ":".join(cola.split(":")[:2])
        return f"{d.strftime('%d/%m/%Y')} {hhmm}"
    return d.strftime("%d/%m/%Y")
