"""
Detecta qué banco produjo el extracto y delega al parser adecuado.
"""
from __future__ import annotations

from pathlib import Path

from app.importers import caixabank, ing
from app.importers.common import ParsedExtract, xls_to_csv_rows


def detect_and_parse(path: Path | str) -> ParsedExtract:
    p = Path(path)
    ext = p.suffix.lower()

    if ext in (".xls", ".xlsx"):
        rows = xls_to_csv_rows(p)
        if ing.matches(rows):
            return ing.parse(p)
        if caixabank.matches(rows):
            return caixabank.parse(p)
        raise ValueError(
            f"Formato XLS no reconocido. {p.name}: no encaja con ING ni CaixaBank."
        )

    raise ValueError(f"Tipo de archivo {ext} no soportado todavía. "
                     f"Soportamos: .xls, .xlsx.")
