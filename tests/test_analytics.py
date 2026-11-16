"""
Tests de los agregados por mes: el rango de un mes y la suma de ingresos y
gastos. Los saldos están en test_balances.py y la curva, en
test_balance_series.py.
"""
import unittest
from datetime import date

from app.services.analytics import month_income_expense, month_range, prev_month_range
from tests.bd_minima import nueva_bd


class TestMonthRange(unittest.TestCase):
    def test_january(self):
        s, e = month_range(date(2026, 1, 15))
        self.assertEqual(s, "2026-01-01")
        self.assertEqual(e, "2026-01-31")

    def test_december(self):
        s, e = month_range(date(2026, 12, 5))
        self.assertEqual(s, "2026-12-01")
        self.assertEqual(e, "2026-12-31")

    def test_february_leap(self):
        s, e = month_range(date(2024, 2, 5))
        self.assertEqual(e, "2024-02-29")

    def test_february_non_leap(self):
        s, e = month_range(date(2025, 2, 5))
        self.assertEqual(e, "2025-02-28")

    def test_prev_month(self):
        s, e = prev_month_range(date(2026, 3, 5))
        self.assertEqual((s, e), ("2026-02-01", "2026-02-28"))
        s, e = prev_month_range(date(2026, 1, 5))
        self.assertEqual((s, e), ("2025-12-01", "2025-12-31"))


class TestMonthIncomeExpense(unittest.TestCase):
    def setUp(self):
        self.con = nueva_bd()
        cur = self.con.cursor()
        cur.execute("INSERT INTO accounts(name, initial_balance) VALUES ('A', 0)")
        cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description, transfer_id) VALUES "
            "(1, '2026-04-05', -50.0, 'compra', NULL),"
            "(1, '2026-04-10',  100.0, 'ingreso', NULL),"
            "(1, '2026-04-15', -25.5, 'café', NULL),"
            "(1, '2026-04-20', -200.0, 'traspaso', 99)"  # excluido por transfer_id
        )
        self.cur = cur

    def tearDown(self):
        self.con.close()

    def test_excludes_transfers(self):
        r = month_income_expense(self.cur, "2026-04-01", "2026-04-30")
        self.assertEqual(r["income"], 100.0)
        self.assertEqual(r["expense"], -75.5)
        self.assertEqual(r["net"], 24.5)

    def test_empty_range(self):
        r = month_income_expense(self.cur, "2025-01-01", "2025-01-31")
        self.assertEqual(r, {"income": 0, "expense": 0, "net": 0})


if __name__ == "__main__":
    unittest.main()
