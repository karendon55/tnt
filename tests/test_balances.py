"""
Tests del saldo de una cuenta: ahora, en una fecha, y el patrimonio.

Las cuentas de inversión son el caso raro: un fondo cambia de valor sin
movimientos, así que su saldo lo marca la última valoración declarada y no la
suma de aportaciones. Importes inventados.
"""
import unittest

from app.services.balances import account_balance, account_balance_at, contributed, total_balance
from tests.bd_minima import nueva_bd


class TestAccountBalance(unittest.TestCase):
    def setUp(self):
        self.con = nueva_bd()
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


class TestCuentasDeInversion(unittest.TestCase):
    """Un fondo cambia de valor sin movimientos: su saldo lo marca la última
    valoración declarada, no la suma de aportaciones."""

    def setUp(self):
        self.con = nueva_bd()
        self.cur = self.con.cursor()
        self.cur.execute(
            "INSERT INTO accounts(id, name, type, initial_balance) "
            "VALUES (1, 'Fondo', 'investment', 50000.0)"
        )
        self.cur.execute(
            "INSERT INTO accounts(id, name, type, initial_balance) "
            "VALUES (2, 'Banco', 'bank', 1000.0)"
        )

    def _valorar(self, fecha, valor, account_id=1):
        self.cur.execute(
            "INSERT INTO account_valuations(account_id, date, value) VALUES (?,?,?)",
            (account_id, fecha, valor),
        )

    def test_sin_valoracion_usa_lo_aportado(self):
        self.assertEqual(account_balance(self.cur, 1), 50000.0)

    def test_la_valoracion_manda_sobre_los_movimientos(self):
        self._valorar("2026-08-31", 51350.75)
        self.assertEqual(account_balance(self.cur, 1), 51350.75)

    def test_rentabilidad_es_valor_menos_aportado(self):
        self._valorar("2026-08-31", 51350.75)
        rent = account_balance(self.cur, 1) - contributed(self.cur, 1)
        self.assertAlmostEqual(rent, 1350.75, places=2)

    def test_una_aportacion_posterior_no_altera_el_valor_declarado(self):
        self._valorar("2026-08-31", 51350.75)
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) "
            "VALUES (1, '2026-09-05', 500.0, 'Aportación')"
        )
        # el valor sigue siendo el declarado; lo aportado sí sube
        self.assertEqual(account_balance(self.cur, 1), 51350.75)
        self.assertEqual(contributed(self.cur, 1), 50500.0)

    def test_un_reembolso_resta_de_lo_aportado(self):
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) "
            "VALUES (1, '2026-09-10', -1440.0, 'Reembolso')"
        )
        self.assertEqual(contributed(self.cur, 1), 48560.0)

    def test_toma_la_valoracion_vigente_en_cada_fecha(self):
        self._valorar("2026-07-31", 51200.40)
        self._valorar("2026-08-31", 51350.75)
        self.assertEqual(account_balance_at(self.cur, 1, "2026-08-15"), 51200.40)
        self.assertEqual(account_balance_at(self.cur, 1, "2026-08-31"), 51350.75)
        # antes de la primera valoración, lo aportado
        self.assertEqual(account_balance_at(self.cur, 1, "2026-06-30"), 50000.0)

    def test_patrimonio_suma_valoracion_y_no_aportaciones(self):
        self._valorar("2026-08-31", 51350.75)
        # 51350.75 del fondo + 1000 del banco
        self.assertEqual(total_balance(self.cur), 52350.75)

    def test_una_cuenta_normal_no_se_ve_afectada(self):
        self._valorar("2026-08-31", 99999.0, account_id=2)   # valoración espuria
        self.assertEqual(account_balance(self.cur, 2), 1000.0)


if __name__ == "__main__":
    unittest.main()
