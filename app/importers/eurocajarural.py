"""
Parser para CSV de EuroCaja Rural ("download.csv" desde la banca online).

Estructura:

    Cuentas > Consultar > Movimientos;
    Movimientos;

    Cuenta;ES69 3081 0729 5150 0027 8567 - GENERAL CUENTAS CORRIENTES;
    Fecha desde;01-05-2026;
    Fecha hasta;02-06-2026;
    Tipo de movimiento;;


    Fecha de ejecución;Fecha valor;Descripción;Importe;Saldo
    18-05-2026 06:00;18-05-2026;LIQUIDACION PLAZO        ;296,25   €;297,21   €;
    14-05-2026 08:58;14-05-2026;DEPOSITO A PLAZO         ;-60000,00   €;0,96   €;
    13-05-2026 08:05;12-05-2026;TRANSFERENCIA JESUS ...  ;30.000,00   €;60.000,96   €;

· Encoding: UTF-8 con BOM.
· Line terminator: CRLF.
· Delimiter: `;`.
· Fechas: `DD-MM-YYYY` o `DD-MM-YYYY HH:MM`.
· Importes: formato español con `€` adjunto (`1.234,56   €`).
· El IBAN viene en la cabecera (fila "Cuenta;…").
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from pathlib import Path

from app.importers.common import (
    ParsedExtract, ParsedTransaction, clean_text, parse_amount, parse_date,
    normalize_iban, short_account_label,
)

EXPECTED_HEADER = ["Fecha de ejecución", "Fecha valor", "Descripción", "Importe", "Saldo"]


def _decode(blob: bytes) -> str:
    """Soporta UTF-8 (con/sin BOM) y latin-1 como fallback."""
    if blob.startswith(b"\xef\xbb\xbf"):
        return blob[3:].decode("utf-8", errors="replace")
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("latin-1", errors="replace")


def _read_rows(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=";")
    return [row for row in reader]


def matches(rows: list[list[str]]) -> bool:
    """Detecta la fila con la cabecera real de movimientos."""
    if not rows:
        return False
    for r in rows[:25]:
        joined = ";".join(clean_text(c) for c in r)
        if all(h in joined for h in
               ("Fecha de ejecución", "Fecha valor", "Descripción", "Importe", "Saldo")):
            return True
    return False


def _find_header_idx(rows: list[list[str]]) -> int | None:
    for i, r in enumerate(rows):
        joined = ";".join(clean_text(c) for c in r)
        if "Fecha de ejecución" in joined and "Importe" in joined and "Saldo" in joined:
            return i
    return None


# La fila "Cuenta;ES69 3081 0729 5150 0027 8567 - GENERAL CUENTAS CORRIENTES;"
# Hacemos un split por " - " para separar IBAN del nombre comercial.


def _extract_account_info(rows: list[list[str]]) -> tuple[str, str]:
    """Devuelve (iban_normalizado, account_name) a partir de la cabecera.

    Busca la fila ``Cuenta;<IBAN> - <nombre>;``. Cuidado con la primera fila
    "Cuentas > Consultar > Movimientos" — también empieza por "cuenta" pero
    no contiene IBAN, así que exigimos que r[1] tenga contenido.
    """
    for r in rows[:15]:
        if not r or len(r) < 2:
            continue
        key = clean_text(r[0]).lower()
        val = clean_text(r[1])
        if key == "cuenta" and val:
            # Split por el primer " - " (separador entre IBAN y nombre).
            if " - " in val:
                iban_raw, name = val.split(" - ", 1)
            else:
                iban_raw, name = val, ""
            return normalize_iban(iban_raw), name.strip()
    return "", ""


def _parse_date_ecr(raw: str) -> date:
    """Acepta 'DD-MM-YYYY' o 'DD-MM-YYYY HH:MM'."""
    s = clean_text(raw)
    if " " in s:
        s = s.split(" ", 1)[0]
    return parse_date(s)


def parse_csv_text(
    text: str,
    *,
    bank: str = "EuroCaja Rural",
    iban: str = "",
    account_name: str = "",
    currency: str = "EUR",
) -> ParsedExtract:
    """Convierte el contenido de un CSV de EuroCaja Rural en un ParsedExtract."""
    rows = _read_rows(text)
    if not matches(rows):
        raise ValueError("El fichero no parece un CSV de EuroCaja Rural.")

    extracted_iban, extracted_name = _extract_account_info(rows)
    iban_final = iban or extracted_iban
    name_final = (
        account_name
        or extracted_name
        or f"EuroCaja Rural {short_account_label(iban_final)}"
    )

    extract = ParsedExtract(
        bank=bank,
        iban=iban_final,
        account_name=name_final,
        currency=currency,
    )

    header_idx = _find_header_idx(rows)
    if header_idx is None:
        return extract  # no hay datos

    header = [clean_text(c) for c in rows[header_idx]]

    def col(row: list[str], name: str) -> str:
        try:
            i = header.index(name)
        except ValueError:
            return ""
        if i >= len(row):
            return ""
        return clean_text(row[i])

    errors: list[tuple[int, str]] = []
    for n, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not any(clean_text(c) for c in row):
            continue
        try:
            d = _parse_date_ecr(col(row, "Fecha de ejecución"))
            vd_raw = col(row, "Fecha valor")
            vd = _parse_date_ecr(vd_raw) if vd_raw else None
            amount = parse_amount(col(row, "Importe"))
            desc = col(row, "Descripción").strip() or "(sin descripción)"

            balance = None
            sal_raw = col(row, "Saldo")
            if sal_raw:
                try:
                    balance = parse_amount(sal_raw)
                except ValueError:
                    pass

            extract.transactions.append(ParsedTransaction(
                date=d,
                value_date=vd,
                amount=amount,
                description=desc,
                memo=None,
                balance=balance,
                source_hint=None,
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append((n, str(exc)))

    if errors:
        extract.parse_errors = errors  # type: ignore[attr-defined]

    return extract


def parse(path: Path) -> ParsedExtract:
    blob = Path(path).read_bytes()
    return parse_csv_text(_decode(blob))
