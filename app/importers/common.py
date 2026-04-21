"""
Utilidades compartidas para todos los parsers de extractos.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

# ====== Normalización de texto ======

# El mojibake que traen los XLS de ING: ¥ en lugar de Ñ
_MOJIBAKE = {
    "¥": "Ñ",
    "PI¥ONERO": "PIÑONERO",
    "ESPA¥A": "ESPAÑA",
    "A¥O": "AÑO",
}

_WS = re.compile(r"\s+")


def clean_text(s: str | None) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    for bad, good in _MOJIBAKE.items():
        s = s.replace(bad, good)
    s = _WS.sub(" ", s)
    return s


# ====== Parseo de importes ======
_AMOUNT_RE = re.compile(r"^-?\d+([.,]\d+)?$")


def parse_amount(raw: str | float | int | None) -> float:
    """
    '-55,38' -> -55.38
    '4046,39' -> 4046.39
    '-35'   -> -35.00
    '-0,24' -> -0.24
    '1.234,56' -> 1234.56 (separador miles con punto, decimal coma)
    """
    if raw is None:
        raise ValueError("importe vacío")
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(" ", "").replace("€", "").replace("EUR", "")
    if not s:
        raise ValueError("importe vacío")
    # Si trae punto y coma, el punto son miles
    if "." in s and "," in s:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    return float(s)


# ====== Parseo de fechas ======
_DATE_FORMATS = [
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
]


def parse_date(raw: str | None) -> date:
    if not raw:
        raise ValueError("fecha vacía")
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"formato de fecha no reconocido: {raw!r}")


# ====== Hash para dedup ======

def tx_hash(*, iban: str, date_iso: str, amount: float, description: str,
            balance: float | None = None) -> str:
    """
    Hash determinista para deduplicar. Incluye saldo cuando está disponible
    porque distingue dos movimientos idénticos del mismo día (raro pero pasa).
    """
    blob = "|".join([
        (iban or "").strip().replace(" ", ""),
        date_iso,
        f"{amount:.2f}",
        clean_text(description).lower(),
        f"{balance:.2f}" if balance is not None else "",
    ])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


# ====== Conversión de .xls antiguo a CSV vía ssconvert ======

def xls_to_csv_rows(xls_path: Path) -> list[list[str]]:
    """
    Convierte un .xls (BIFF) a filas CSV vía ssconvert (Gnumeric).
    Devuelve lista de filas (cada fila = lista de celdas como str).
    """
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.csv"
        res = subprocess.run(
            ["ssconvert", "--export-type=Gnumeric_stf:stf_csv",
             str(xls_path), str(out)],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            raise RuntimeError(f"ssconvert falló: {res.stderr}")
        import csv
        with out.open(encoding="utf-8") as f:
            return [row for row in csv.reader(f)]


# ====== Estructura que devuelve cada parser ======

@dataclass
class ParsedTransaction:
    date: date
    value_date: date | None
    amount: float
    description: str
    memo: str | None = None
    balance: float | None = None
    source_hint: str | None = None  # categoría original del banco si viene


@dataclass
class ParsedExtract:
    bank: str
    iban: str
    account_name: str
    currency: str
    transactions: list[ParsedTransaction] = field(default_factory=list)


# ====== Normalizar IBAN/número de cuenta ======

def normalize_iban(raw: str) -> str:
    return re.sub(r"\s+", "", str(raw or "").upper())


def short_account_label(iban: str) -> str:
    """'ES16 2100 2504 6313 0042 5498' -> '****5498'."""
    digits = re.sub(r"\D", "", iban or "")
    tail = digits[-4:] if len(digits) >= 4 else digits
    return f"****{tail}" if tail else "cuenta"
