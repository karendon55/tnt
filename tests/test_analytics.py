"""
Tests para los cálculos agregados en BD: account_balance, account_balance_at,
month_range, prev_month_range y month_income_expense.

Usamos una BD SQLite en memoria con el esquema mínimo necesario.
"""
import sqlite3
import unittest
from datetime import date

from app.services.analytics import (
    account_balance, account_balance_at, month_income_expense,
    month_range, prev_month_range, total_balance,
)


def _new_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            initial_balance REAL NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            transfer_id INTEGER
        );
    """)
    return con


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


class TestAccountBalance(unittest.TestCase):
    def setUp(self):
        self.con = _new_db()
        cur = self.con.cursor()
        cur.execute("INSERT INTO accounts(name, initial_balance) VALUES ('A', 1000.0)")
        cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) VALUES "
            "(1, '2026-01-10', -100.0, 'compra'),"
            "(1, '2026-02-15',  500.0, 'ingreso'),"
            "(1, '2026-03-20', -50.5,  'café')"
        )
        self.cur = cur

    def tearDown(self):
        self.con.close()

    def test_balance_now(self):
        # 1000 - 100 + 500 - 50.5 = 1349.5
        self.assertEqual(account_balance(self.cur, 1), 1349.5)

    def test_balance_at_specific_date(self):
        # Hasta 2026-01-31: 1000 - 100 = 900
        self.assertEqual(account_balance_at(self.cur, 1, "2026-01-31"), 900.0)
        # Hasta 2026-02-28: 1000 - 100 + 500 = 1400
        self.assertEqual(account_balance_at(self.cur, 1, "2026-02-28"), 1400.0)
        # Hasta 2026-04-01: incluye todo
        self.assertEqual(account_balance_at(self.cur, 1, "2026-04-01"), 1349.5)
        # Antes del primer movimiento: solo el saldo inicial
        self.assertEqual(account_balance_at(self.cur, 1, "2025-12-31"), 1000.0)

    def test_balance_unknown_account(self):
        self.assertEqual(account_balance(self.cur, 999), 0)
        self.assertEqual(account_balance_at(self.cur, 999, "2026-01-01"), 0)

    def test_total_balance_excludes_archived(self):
        cur = self.cur
        cur.execute("INSERT INTO accounts(name, initial_balance, archived) VALUES ('B', 500.0, 0)")
        cur.execute("INSERT INTO accounts(name, initial_balance, archived) VALUES ('C-arch', 9999.0, 1)")
        # total = (1000 + 500) + (-100 + 500 - 50.5) = 1849.5
        self.assertEqual(total_balance(cur), 1849.5)


class TestMonthIncomeExpense(unittest.TestCase):
    def setUp(self):
        self.con = _new_db()
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
