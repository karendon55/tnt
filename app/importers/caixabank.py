"""
Parser para extractos XLS de CaixaBank.

Estructura:
  Fila 1: "Movimientos de la cuenta ES16 2100 2504 ... (CCC: ...)"
  Fila 2: "Importes expresados en euros"
  Fila 3: "Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"
  Filas 4+: datos
"""
from __future__ import annotations

import re
from pathlib import Path

from app.importers.common import (
    ParsedExtract, ParsedTransaction, clean_text, parse_amount, parse_date,
    normalize_iban, short_account_label, xls_to_csv_rows,
)

_IBAN_RE = re.compile(r"(ES\d{2}(?:\s?\d{4}){5})", re.I)


def matches(rows: list[list[str]]) -> bool:
    if len(rows) < 3:
        return False
    head = " ".join(clean_text(c) for c in rows[0])
    col3 = " ".join(clean_text(c) for c in rows[2])
    return (
        "Movimientos de la cuenta" in head
        and "Fecha" in col3
        and "Movimiento" in col3
    )


def parse(xls_path: Path) -> ParsedExtract:
    rows = xls_to_csv_rows(xls_path)
    if not matches(rows):
        raise ValueError("No parece un extracto CaixaBank")

    head_text = " ".join(clean_text(c) for c in rows[0])
    m = _IBAN_RE.search(head_text)
    iban = normalize_iban(m.group(1)) if m else ""

    extract = ParsedExtract(
        bank="CaixaBank",
        iban=iban,
        account_name=f"CaixaBank {short_account_label(iban)}",
        currency="EUR",
    )

    header = [clean_text(c) for c in rows[2]]
    col_idx = {name.lower(): i for i, name in enumerate(header) if name}

    def col(row: list[str], name: str) -> str:
        i = col_idx.get(name.lower())
        return clean_text(row[i]) if i is not None and i < len(row) else ""

    for row in rows[3:]:
        if not any(clean_text(c) for c in row):
            continue
        try:
            d = parse_date(col(row, "Fecha"))
            amount = parse_amount(col(row, "Importe"))
        except ValueError:
            continue
        try:
            vd = parse_date(col(row, "Fecha valor"))
        except ValueError:
            vd = d
        desc = col(row, "Movimiento")
        memo = col(row, "Más datos") or None
        saldo = None
        try:
            saldo = parse_amount(col(row, "Saldo"))
        except ValueError:
            pass

        extract.transactions.append(ParsedTransaction(
            date=d,
            value_date=vd,
            amount=amount,
            description=desc,
            memo=memo,
            balance=saldo,
            source_hint=None,
        ))

    return extract
