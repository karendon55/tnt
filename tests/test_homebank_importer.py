"""
Tests del parser de CSV de HomeBank.
"""
import unittest
from datetime import date

from app.importers.homebank import (
    _decode, matches, parse_csv_text,
)


CSV_BASIC = """date;payment;info;payee;memo;amount;category;tags
01/03/2026;;;;Intereses a tu favor;122,24;Intereses;
05/03/2026;;;;Pago en MARKET BOLIVAR MADRID ES;-4,08;;
10/03/2026;;;;Pago en LIDL ANCORA MADRID ES;-8,65;Alimentación;
"""

CSV_WITH_PAYEE = """date;payment;info;payee;memo;amount;category;tags
01/04/2026;8;Tarjeta;MERCADONA;Compra mensual;-72,30;Alimentación;casa
"""


class TestMatches(unittest.TestCase):
    def test_standard_header(self):
        rows = [["date", "payment", "info", "payee", "memo", "amount", "category", "tags"]]
        self.assertTrue(matches(rows))

    def test_subset_header_with_only_required(self):
        rows = [["date", "memo", "amount", "category"]]
        self.assertTrue(matches(rows))

    def test_missing_amount(self):
        rows = [["date", "memo", "category"]]
        self.assertFalse(matches(rows))

    def test_missing_date(self):
        rows = [["memo", "amount", "category"]]
        self.assertFalse(matches(rows))

    def test_empty(self):
        self.assertFalse(matches([]))

    def test_random_first_row(self):
        rows = [["foo", "bar", "baz"]]
        self.assertFalse(matches(rows))

    def test_only_required_no_extras(self):
        # Necesita además tener al menos uno de category/payee/payment
        rows = [["date", "memo", "amount"]]
        self.assertFalse(matches(rows))


class TestParseCsv(unittest.TestCase):
    def test_three_rows_parsed(self):
        ext = parse_csv_text(CSV_BASIC, account_name="Test")
        self.assertEqual(ext.bank, "HomeBank")
        self.assertEqual(ext.account_name, "Test")
        self.assertEqual(len(ext.transactions), 3)

    def test_dates_and_amounts(self):
        ext = parse_csv_text(CSV_BASIC)
        t1, t2, t3 = ext.transactions
        self.assertEqual(t1.date, date(2026, 3, 1))
        self.assertEqual(t1.amount, 122.24)
        self.assertEqual(t2.amount, -4.08)
        self.assertEqual(t3.amount, -8.65)

    def test_source_hint_from_category(self):
        ext = parse_csv_text(CSV_BASIC)
        self.assertEqual(ext.transactions[0].source_hint, "Intereses")
        self.assertIsNone(ext.transactions[1].source_hint)
        self.assertEqual(ext.transactions[2].source_hint, "Alimentación")

    def test_payee_prepended_to_description(self):
        ext = parse_csv_text(CSV_WITH_PAYEE)
        tx = ext.transactions[0]
        self.assertEqual(tx.date, date(2026, 4, 1))
        self.assertIn("MERCADONA", tx.description)
        self.assertIn("Compra mensual", tx.description)

    def test_extras_to_memo(self):
        ext = parse_csv_text(CSV_WITH_PAYEE)
        tx = ext.transactions[0]
        # info "Tarjeta" y tags "casa" no están en description → van a memo
        self.assertIsNotNone(tx.memo)
        self.assertIn("Tarjeta", tx.memo)
        self.assertIn("casa", tx.memo)

    def test_skip_blank_lines(self):
        csv = "date;payment;info;payee;memo;amount;category;tags\n" \
              "01/03/2026;;;;Test;1,00;;\n" \
              "\n" \
              ";;;;;;;\n" \
              "02/03/2026;;;;Test 2;2,00;;\n"
        ext = parse_csv_text(csv)
        self.assertEqual(len(ext.transactions), 2)

    def test_bad_row_does_not_abort(self):
        csv = "date;payment;info;payee;memo;amount;category;tags\n" \
              "01/03/2026;;;;Buena;1,00;;\n" \
              "no-soy-fecha;;;;Mala;2,00;;\n" \
              "03/03/2026;;;;Otra buena;3,00;;\n"
        ext = parse_csv_text(csv)
        self.assertEqual(len(ext.transactions), 2)
        self.assertTrue(hasattr(ext, "parse_errors"))
        self.assertEqual(len(ext.parse_errors), 1)
        n, _ = ext.parse_errors[0]
        self.assertEqual(n, 3)

    def test_non_homebank_csv_raises(self):
        csv = "foo;bar;baz\n1;2;3\n"
        with self.assertRaises(ValueError):
            parse_csv_text(csv)

    def test_iban_and_account_name_propagated(self):
        ext = parse_csv_text(
            CSV_BASIC,
            iban="ES1612345678901234567890",
            account_name="Mi cuenta",
            bank="ING",
        )
        self.assertEqual(ext.iban, "ES1612345678901234567890")
        self.assertEqual(ext.account_name, "Mi cuenta")
        self.assertEqual(ext.bank, "ING")


class TestDecode(unittest.TestCase):
    def test_utf8_bom_stripped(self):
        text = _decode(b"\xef\xbb\xbfdate;memo;amount\n01/01/2026;test;1,00\n")
        self.assertTrue(text.startswith("date"))

    def test_latin1_fallback(self):
        # 'ó' en latin-1 es 0xF3, no es UTF-8 válido
        text = _decode(b"category\nAlimentaci\xf3n\n")
        self.assertIn("Alimentación", text)

    def test_utf8_works(self):
        text = _decode("Alimentación\n".encode("utf-8"))
        self.assertIn("Alimentación", text)


class TestCommaDelimiterFallback(unittest.TestCase):
    def test_csv_with_commas_works(self):
        # Algunos exports raros usan ',' en lugar de ';'
        csv = "date,payment,info,payee,memo,amount,category,tags\n" \
              "01/03/2026,,,,Test,1.00,,\n"
        ext = parse_csv_text(csv)
        self.assertEqual(len(ext.transactions), 1)
        self.assertEqual(ext.transactions[0].amount, 1.0)


if __name__ == "__main__":
    unittest.main()
