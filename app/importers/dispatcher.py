"""
Detecta qué banco produjo el extracto y delega al parser adecuado.
"""
from __future__ import annotations

from pathlib import Path

from app.importers import caixabank, eurocajarural, ing
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

    if ext == ".csv":
        blob = Path(p).read_bytes()
        text = eurocajarural._decode(blob)
        rows = eurocajarural._read_rows(text)
        if eurocajarural.matches(rows):
            return eurocajarural.parse(p)
        # Nota: HomeBank tiene su propio endpoint /importar/homebank con
        # selector de cuenta destino — no lo metemos aquí para no confundirlo.
        raise ValueError(
            f"Formato CSV no reconocido. {p.name}: no parece de EuroCaja Rural. "
            f"Si es un CSV de HomeBank, usa la sección 'Importar histórico de HomeBank'."
        )

    raise ValueError(f"Tipo de archivo {ext} no soportado todavía. "
                     f"Soportamos: .xls, .xlsx, .csv.")
