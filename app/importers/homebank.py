"""
Importador de CSV de HomeBank.

Formato del CSV (separado por ;):

    date;payment;info;payee;memo;amount;category;tags
    28/02/2026;;;;Pago en MARKET BOLIVAR MADRID ES;-4,08;;
    01/03/2026;;;;Intereses a tu favor;122,24;Intereses;

  · date     — DD/MM/YYYY
  · payment  — modo de pago (8=tarjeta, 11=transferencia, ...). Suele venir vacío
               en los CSV de "carga" creados por el flujo HomeBank.
  · info     — texto adicional opcional.
  · payee    — beneficiario (opcional).
  · memo     — descripción del movimiento. Es lo que TNT usa como description.
  · amount   — importe con coma decimal. Negativo gasto, positivo ingreso.
  · category — categoría asignada en HomeBank (opcional). Se pasa como source_hint.
  · tags     — etiquetas separadas por coma (opcional).

A diferencia de los extractos del banco, el CSV de HomeBank no contiene IBAN
ni saldo. El usuario debe seleccionar la cuenta destino en el momento de
importar; el parser construye un ParsedExtract con esa cuenta.

Aceptamos UTF-8, UTF-8 con BOM y latin-1 (los exports de HomeBank en español
suelen estar en latin-1 si la BBDD del usuario es antigua).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from app.importers.common import (
    ParsedExtract, ParsedTransaction, clean_text, parse_amount, parse_date,
)

EXPECTED_HEADER = ["date", "payment", "info", "payee", "memo", "amount", "category", "tags"]


def _decode(blob: bytes) -> str:
    """Detecta y decodifica el contenido en utf-8 / utf-8-bom / latin-1."""
    if blob.startswith(b"\xef\xbb\xbf"):
        return blob[3:].decode("utf-8", errors="replace")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1", errors="replace")


def _read_rows(text: str) -> list[list[str]]:
    """Devuelve filas del CSV con separador ';'. Tolera ',' como fallback si no
    hay ningún ';' en la primera línea (algunos exports raros)."""
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if ";" in first_line else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(c.strip() for c in row)]


def matches(rows: list[list[str]]) -> bool:
    """Heurística: la primera fila debe ser la cabecera estándar de HomeBank."""
    if not rows:
        return False
    head = [clean_text(c).lower() for c in rows[0]]
    # Aceptamos cualquier orden subset que contenga estas columnas clave
    must_have = {"date", "memo", "amount"}
    return must_have.issubset(set(head)) and (
        "category" in head or "payee" in head or "payment" in head
    )


def parse_csv_text(
    text: str,
    *,
    bank: str = "HomeBank",
    iban: str = "",
    account_name: str = "HomeBank import",
    currency: str = "EUR",
) -> ParsedExtract:
    """Convierte el texto de un CSV de HomeBank en un ParsedExtract.

    No deduplica ni inserta — eso es trabajo del servicio ingest.
    """
    rows = _read_rows(text)
    if not matches(rows):
        raise ValueError("El fichero no tiene la cabecera de un CSV de HomeBank.")

    header = [clean_text(c).lower() for c in rows[0]]
    idx = {col: header.index(col) for col in header}

    def cell(row, key, default=""):
        i = idx.get(key)
        if i is None or i >= len(row):
            return default
        return row[i]

    extract = ParsedExtract(
        bank=bank,
        iban=iban,
        account_name=account_name,
        currency=currency,
    )

    errors: list[tuple[int, str]] = []
    for n, row in enumerate(rows[1:], start=2):
        try:
            d_raw = clean_text(cell(row, "date"))
            if not d_raw:
                continue  # filas en blanco
            d = parse_date(d_raw)

            amt_raw = clean_text(cell(row, "amount"))
            if not amt_raw:
                continue
            amount = parse_amount(amt_raw)

            memo = clean_text(cell(row, "memo"))
            payee = clean_text(cell(row, "payee"))
            info = clean_text(cell(row, "info"))
            cat = clean_text(cell(row, "category"))
            tags = clean_text(cell(row, "tags"))

            # Construimos description y memo:
            #   - Si memo está, es la descripción principal.
            #   - Si payee está y no está incluido en memo, lo prefijamos.
            #   - El campo memo de TNT recoge info+tags si los hay.
            description = memo or payee or info or "(sin descripción)"
            if payee and payee not in description:
                description = f"{payee} · {description}"

            extras = [x for x in (info, tags) if x and x not in description]
            tnt_memo = " · ".join(extras) if extras else None

            extract.transactions.append(ParsedTransaction(
                date=d,
                value_date=None,
                amount=amount,
                description=description,
                memo=tnt_memo,
                balance=None,
                source_hint=cat or None,
            ))
        except Exception as e:  # noqa: BLE001 — queremos saltar filas malas, no abortar
            errors.append((n, str(e)))

    # Guardamos los errores no críticos en un atributo dinámico —
    # no rompe ParsedExtract y los routers pueden mostrarlos.
    if errors:
        extract.parse_errors = errors  # type: ignore[attr-defined]

    return extract


def parse_csv_file(path: Path, **kwargs) -> ParsedExtract:
    blob = Path(path).read_bytes()
    return parse_csv_text(_decode(blob), **kwargs)
