"""
Helpers de parseo de formularios compartidos entre routers.
"""
from __future__ import annotations

from typing import Optional


def to_int_or_none(value: Optional[str]) -> Optional[int]:
    """Convierte '' o None a None, números a int. Silenciosa ante basura."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
