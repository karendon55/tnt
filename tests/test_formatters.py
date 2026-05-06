"""
Tests del formato es-ES (miles con '.', decimales con ',').
"""
import unittest

from app.utils.formatters import eur, eur_signed, num_es, pct_signed


class TestNumEs(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(num_es(0), "0,00")
        self.assertEqual(num_es(1), "1,00")
        self.assertEqual(num_es(1.5), "1,50")

    def test_thousands(self):
        self.assertEqual(num_es(1234.56), "1.234,56")
        self.assertEqual(num_es(197836.15), "197.836,15")
        self.assertEqual(num_es(1000000), "1.000.000,00")

    def test_negative(self):
        self.assertEqual(num_es(-1.5), "-1,50")
        self.assertEqual(num_es(-1234.56), "-1.234,56")

    def test_decimals_param(self):
        self.assertEqual(num_es(1234.567, decimals=3), "1.234,567")
        # decimales=0 trunca según el redondeo bancario de Python (banker's
        # rounding); 1234.6 evita la ambigüedad de 1234.5.
        self.assertEqual(num_es(1234.6, decimals=0), "1.235")

    def test_none_and_invalid(self):
        self.assertEqual(num_es(None), "")
        self.assertEqual(num_es(""), "")
        self.assertEqual(num_es("xx"), "")


class TestEur(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(eur(0), "0,00 €")
        self.assertEqual(eur(62.5), "62,50 €")
        self.assertEqual(eur(197836.15), "197.836,15 €")

    def test_negative(self):
        self.assertEqual(eur(-2.49), "-2,49 €")

    def test_none(self):
        self.assertEqual(eur(None), "")


class TestEurSigned(unittest.TestCase):
    def test_positive_has_plus(self):
        self.assertEqual(eur_signed(0), "+0,00 €")
        self.assertEqual(eur_signed(62.5), "+62,50 €")

    def test_negative_has_minus(self):
        self.assertEqual(eur_signed(-2.49), "-2,49 €")
        self.assertEqual(eur_signed(-1234.5), "-1.234,50 €")


class TestPctSigned(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(pct_signed(0), "+0,0%")
        self.assertEqual(pct_signed(1.5), "+1,5%")
        self.assertEqual(pct_signed(-1.5), "-1,5%")

    def test_decimals_param(self):
        self.assertEqual(pct_signed(1.234, decimals=2), "+1,23%")


if __name__ == "__main__":
    unittest.main()
