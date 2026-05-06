"""
Tests para los parsers de extractos.

  · Comunes: parse_amount, parse_date, clean_text, tx_hash, normalize_iban,
    short_account_label.
  · ING: matches() detecta el formato; parse() extrae campos correctos
    a partir de un CSV sintético (monkeypatch de xls_to_csv_rows).
  · CaixaBank: idéntico patrón.
"""
import unittest
from datetime import date
from unittest.mock import patch

from app.importers import caixabank, ing
from app.importers.common import (
    clean_text, normalize_iban, parse_amount, parse_date,
    short_account_label, tx_hash,
)


class TestCommon(unittest.TestCase):
    def test_clean_text_collapses_spaces_and_fixes_mojibake(self):
        self.assertEqual(clean_text("  ESPA¥A   tour  "), "ESPAÑA tour")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(123), "123")

    def test_parse_amount_es_format(self):
        self.assertEqual(parse_amount("-55,38"), -55.38)
        self.assertEqual(parse_amount("4046,39"), 4046.39)
        self.assertEqual(parse_amount("-35"), -35.0)
        self.assertEqual(parse_amount("1.234,56"), 1234.56)
        self.assertEqual(parse_amount("-0,24"), -0.24)
        self.assertEqual(parse_amount(12.5), 12.5)
        self.assertEqual(parse_amount("12,50 €"), 12.5)

    def test_parse_amount_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_amount(None)
        with self.assertRaises(ValueError):
            parse_amount("")

    def test_parse_date_multiple_formats(self):
        self.assertEqual(parse_date("2026-04-24"), date(2026, 4, 24))
        self.assertEqual(parse_date("24/04/2026"), date(2026, 4, 24))
        self.assertEqual(parse_date("24-04-2026"), date(2026, 4, 24))
        self.assertEqual(parse_date("2026/04/24"), date(2026, 4, 24))

    def test_parse_date_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_date("hola")
        with self.assertRaises(ValueError):
            parse_date(None)

    def test_tx_hash_is_deterministic_and_unique(self):
        h1 = tx_hash(iban="ES12", date_iso="2026-04-01", amount=-12.5,
                     description="CAFE", balance=100.0)
        h2 = tx_hash(iban="ES12", date_iso="2026-04-01", amount=-12.5,
                     description="CAFE", balance=100.0)
        h3 = tx_hash(iban="ES12", date_iso="2026-04-01", amount=-12.5,
                     description="CAFE", balance=87.5)
        self.assertEqual(h1, h2, "hash debe ser determinista")
        self.assertNotEqual(h1, h3, "saldo distinto debe dar hash distinto")

    def test_normalize_iban(self):
        self.assertEqual(normalize_iban("ES16 2100 2504 1234"),
                         "ES16210025041234")
        self.assertEqual(normalize_iban("  es16 2100  "), "ES162100")
        self.assertEqual(normalize_iban(None), "")

    def test_short_account_label(self):
        self.assertEqual(short_account_label("ES16210025045498"), "****5498")
        self.assertEqual(short_account_label(""), "cuenta")
        self.assertEqual(short_account_label("ES1"), "****1")


# ====== Fixtures sintéticas para los parsers ======

ING_ROWS = [
    ["Movimientos de la Cuenta", "", "  Número de cuenta:", "ES16 1234 5678 9012 3456 7890"],
    ["", "", "  Titular:", "Test"],
    ["", "", "  Fecha exportación:", "2026-04-24"],
    ["F. VALOR", "CATEGORÍA", "SUBCATEGORÍA", "DESCRIPCIÓN",
     "COMENTARIO", "IMPORTE (€)", "SALDO (€)"],
    ["2026-04-15", "Alimentación", "Supermercados", "MERCADONA MADRID",
     "", "-42,50", "1.234,56"],
    ["2026-04-10", "Ingresos", "Nómina", "TRANSFERENCIA NOMINA",
     "abril", "1500,00", "1.277,06"],
    ["", "", "", "", "", "", ""],  # fila vacía -> debe ignorarse
]

CAIXA_ROWS = [
    ["Movimientos de la cuenta ES16 2100 2504 6313 0042 5498 (CCC: 21002504...)"],
    ["Importes expresados en euros"],
    ["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"],
    ["12/04/2026", "12/04/2026", "PAGO TARJETA", "BAR DE TAPAS", "-15,80", "987,65"],
    ["10/04/2026", "10/04/2026", "BIZUM RECIBIDO", "OLGA", "30,00", "1.003,45"],
    ["", "", "", "", "", ""],
]


class TestIngParser(unittest.TestCase):
    def test_matches_true(self):
        self.assertTrue(ing.matches(ING_ROWS))

    def test_matches_false(self):
        self.assertFalse(ing.matches([["foo"], ["bar"]]))
        self.assertFalse(ing.matches(CAIXA_ROWS))

    def test_parse_extracts_transactions(self):
        with patch("app.importers.ing.xls_to_csv_rows", return_value=ING_ROWS):
            extract = ing.parse("/tmp/fake.xls")
        self.assertEqual(extract.bank, "ING")
        self.assertEqual(extract.iban, "ES1612345678901234567890")
        self.assertEqual(extract.account_name, "ING ****7890")
        self.assertEqual(len(extract.transactions), 2)

        t1 = extract.transactions[0]
        self.assertEqual(t1.date, date(2026, 4, 15))
        self.assertEqual(t1.amount, -42.50)
        self.assertEqual(t1.description, "MERCADONA MADRID")
        self.assertEqual(t1.balance, 1234.56)
        self.assertEqual(t1.source_hint, "Alimentación|Supermercados")

        t2 = extract.transactions[1]
        self.assertEqual(t2.amount, 1500.00)
        self.assertEqual(t2.memo, "abril")


class TestCaixaParser(unittest.TestCase):
    def test_matches_true(self):
        self.assertTrue(caixabank.matches(CAIXA_ROWS))

    def test_matches_false(self):
        self.assertFalse(caixabank.matches(ING_ROWS))
        self.assertFalse(caixabank.matches([["x"]]))

    def test_parse_extracts_transactions(self):
        with patch("app.importers.caixabank.xls_to_csv_rows", return_value=CAIXA_ROWS):
            extract = caixabank.parse("/tmp/fake.xls")
        self.assertEqual(extract.bank, "CaixaBank")
        self.assertEqual(extract.iban, "ES16210025046313004254 98".replace(" ", ""))
        self.assertEqual(extract.account_name, "CaixaBank ****5498")
        self.assertEqual(len(extract.transactions), 2)

        t1 = extract.transactions[0]
        self.assertEqual(t1.date, date(2026, 4, 12))
        self.assertEqual(t1.amount, -15.80)
        self.assertEqual(t1.description, "PAGO TARJETA")
        self.assertEqual(t1.memo, "BAR DE TAPAS")
        self.assertEqual(t1.balance, 987.65)

        t2 = extract.transactions[1]
        self.assertEqual(t2.amount, 30.00)
        self.assertEqual(t2.description, "BIZUM RECIBIDO")


if __name__ == "__main__":
    unittest.main()
