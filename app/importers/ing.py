"""
Parser para extractos XLS de ING (generados por JasperReports).

Estructura:
  Fila 1: "Movimientos de la Cuenta", "", "  Número de cuenta:", "<num>"
  Fila 2: "", "", "  Titular:", "<nombre>"
  Fila 3: "", "", "  Fecha exportación:", "<fecha>"
  Fila 4: "F. VALOR", "CATEGORÍA", "SUBCATEGORÍA", "DESCRIPCIÓN",
          "COMENTARIO", "IMPORTE (€)", "SALDO (€)"
  Filas 5+: datos
"""
from __future__ import annotations

from pathlib import Path

from app.importers.common import (
    ParsedExtract, ParsedTransaction, clean_text, parse_amount, parse_date,
    normalize_iban, short_account_label, xls_to_csv_rows,
)


def matches(rows: list[list[str]]) -> bool:
    if len(rows) < 4:
        return False
    head = " ".join(clean_text(c) for c in rows[0])
    col4 = " ".join(clean_text(c) for c in rows[3])
    return (
        "Movimientos de la Cuenta" in head
        and "F. VALOR" in col4
        and "CATEGOR" in col4
    )


def parse(xls_path: Path) -> ParsedExtract:
    rows = xls_to_csv_rows(xls_path)
    if not matches(rows):
        raise ValueError("No parece un extracto ING")

    # Extraer nº cuenta de la cabecera
    iban = ""
    for cell in rows[0]:
        t = clean_text(cell)
        if t and any(c.isdigit() for c in t) and "cuenta" not in t.lower():
            iban = normalize_iban(t)
            break

    extract = ParsedExtract(
        bank="ING",
        iban=iban,
        account_name=f"ING {short_account_label(iban)}",
        currency="EUR",
    )

    header = [clean_text(c).upper() for c in rows[3]]
    col_idx = {name: i for i, name in enumerate(header) if name}

    def col(row: list[str], *names: str) -> str:
        for name in names:
            i = col_idx.get(name)
            if i is not None and i < len(row):
                return clean_text(row[i])
        return ""

    for row in rows[4:]:
        if not any(clean_text(c) for c in row):
            continue
        try:
            d = parse_date(col(row, "F. VALOR"))
            amount = parse_amount(col(row, "IMPORTE (€)", "IMPORTE"))
        except ValueError:
            continue  # fila vacía o cabecera repetida
        desc = col(row, "DESCRIPCIÓN")
        memo = col(row, "COMENTARIO") or None
        saldo = None
        try:
            saldo = parse_amount(col(row, "SALDO (€)", "SALDO"))
        except ValueError:
            pass
        cat = clean_text(col(row, "CATEGORÍA"))
        sub = clean_text(col(row, "SUBCATEGORÍA"))
        hint = f"{cat}|{sub}" if sub else cat if cat else None

        extract.transactions.append(ParsedTransaction(
            date=d,
            value_date=d,
            amount=amount,
            description=desc,
            memo=memo,
            balance=saldo,
            source_hint=hint,
        ))

    return extract
