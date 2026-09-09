"""
Tests para los cálculos agregados en BD: account_balance, account_balance_at,
month_range, prev_month_range y month_income_expense.

Usamos una BD SQLite en memoria con el esquema mínimo necesario.
"""
import sqlite3
import unittest
from datetime import date

from app.services.analytics import (
    account_balance,
    balance_series,
    account_balance_at,
    contributed,
    last_valuation,
    month_income_expense,
    month_range,
    prev_month_range,
    total_balance,
)


def _new_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'bank',
            initial_balance REAL NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE account_valuations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            note TEXT,
            UNIQUE(account_id, date)
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



class TestCuentasDeInversion(unittest.TestCase):
    """Un fondo cambia de valor sin movimientos: su saldo lo marca la última
    valoración declarada, no la suma de aportaciones."""

    def setUp(self):
        self.con = _new_db()
        self.cur = self.con.cursor()
        self.cur.execute(
            "INSERT INTO accounts(id, name, type, initial_balance) "
            "VALUES (1, 'Indexa Capital', 'investment', 60440.0)"
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
        self.assertEqual(account_balance(self.cur, 1), 60440.0)

    def test_la_valoracion_manda_sobre_los_movimientos(self):
        self._valorar("2026-08-31", 63334.26)
        self.assertEqual(account_balance(self.cur, 1), 63334.26)

    def test_rentabilidad_es_valor_menos_aportado(self):
        self._valorar("2026-08-31", 63334.26)
        rent = account_balance(self.cur, 1) - contributed(self.cur, 1)
        self.assertAlmostEqual(rent, 2894.26, places=2)

    def test_una_aportacion_posterior_no_altera_el_valor_declarado(self):
        self._valorar("2026-08-31", 63334.26)
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) "
            "VALUES (1, '2026-09-05', 500.0, 'Aportación')"
        )
        # el valor sigue siendo el declarado; lo aportado sí sube
        self.assertEqual(account_balance(self.cur, 1), 63334.26)
        self.assertEqual(contributed(self.cur, 1), 60940.0)

    def test_un_reembolso_resta_de_lo_aportado(self):
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) "
            "VALUES (1, '2026-09-10', -1440.0, 'Reembolso')"
        )
        self.assertEqual(contributed(self.cur, 1), 59000.0)

    def test_toma_la_valoracion_vigente_en_cada_fecha(self):
        self._valorar("2026-07-31", 63219.43)
        self._valorar("2026-08-31", 63334.26)
        self.assertEqual(account_balance_at(self.cur, 1, "2026-08-15"), 63219.43)
        self.assertEqual(account_balance_at(self.cur, 1, "2026-08-31"), 63334.26)
        # antes de la primera valoración, lo aportado
        self.assertEqual(account_balance_at(self.cur, 1, "2026-06-30"), 60440.0)

    def test_patrimonio_suma_valoracion_y_no_aportaciones(self):
        self._valorar("2026-08-31", 63334.26)
        # 63334.26 del fondo + 1000 del banco
        self.assertEqual(total_balance(self.cur), 64334.26)

    def test_una_cuenta_normal_no_se_ve_afectada(self):
        self._valorar("2026-08-31", 99999.0, account_id=2)   # valoración espuria
        self.assertEqual(account_balance(self.cur, 2), 1000.0)


class TestBalanceSeries(unittest.TestCase):
    """La serie del panel: saldo acumulado al cierre de cada mes.

    Regresión: la serie se construía hasta el mes actual del calendario y
    luego cortaba los últimos N meses, así que con extractos atrasados la
    ventana se llenaba de meses arrastrados y devolvía una recta.
    """

    def setUp(self):
        self.con = _new_db()
        self.cur = self.con.cursor()
        self.cur.execute(
            "INSERT INTO accounts(id, name, initial_balance) VALUES (1, 'Banco', 1000.0)"
        )
        # Enero y febrero con movimientos, marzo vacío, abril con movimiento.
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) VALUES "
            "(1, '2026-01-10', -100.0, 'compra'),"
            "(1, '2026-02-15',  500.0, 'nómina'),"
            "(1, '2026-04-20',  -50.5, 'café')"
        )

    def tearDown(self):
        self.con.close()

    def test_un_valor_distinto_y_correcto_por_mes(self):
        serie = balance_series(self.cur, months=6)
        self.assertEqual(
            serie,
            [
                {"month": "2026-01", "balance": 900.0},    # 1000 - 100
                {"month": "2026-02", "balance": 1400.0},   # 900 + 500
                {"month": "2026-03", "balance": 1400.0},   # sin movimientos: arrastra
                {"month": "2026-04", "balance": 1349.5},   # 1400 - 50.5
            ],
        )

    def test_un_mes_sin_movimientos_mantiene_el_saldo_anterior(self):
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        self.assertIn("2026-03", por_mes)
        self.assertEqual(por_mes["2026-03"], por_mes["2026-02"])
        self.assertNotEqual(por_mes["2026-03"], 0)

    def test_la_serie_termina_en_el_ultimo_mes_con_datos(self):
        # Con extractos que se quedan atrás, la ventana no se estira hasta hoy
        # rellenando de meses planos.
        serie = balance_series(self.cur, months=6)
        self.assertEqual(serie[0]["month"], "2026-01")
        self.assertEqual(serie[-1]["month"], "2026-04")

    def test_la_serie_no_es_una_recta(self):
        valores = [p["balance"] for p in balance_series(self.cur, months=6)]
        self.assertGreater(len(set(valores)), 1)

    def test_el_ultimo_punto_es_el_patrimonio(self):
        serie = balance_series(self.cur, months=6)
        self.assertEqual(serie[-1]["balance"], total_balance(self.cur))

    def test_respeta_el_limite_de_meses(self):
        serie = balance_series(self.cur, months=2)
        self.assertEqual([p["month"] for p in serie], ["2026-03", "2026-04"])

    def test_sin_movimientos_devuelve_vacio(self):
        con = _new_db()
        cur = con.cursor()
        cur.execute("INSERT INTO accounts(name, initial_balance) VALUES ('Vacía', 10.0)")
        self.assertEqual(balance_series(cur, months=6), [])
        con.close()

    def test_las_cuentas_archivadas_no_mueven_la_serie(self):
        # Su saldo inicial no entra en el patrimonio, así que sus movimientos
        # tampoco deben mover la curva.
        self.cur.execute(
            "INSERT INTO accounts(id, name, initial_balance, archived) "
            "VALUES (2, 'Vieja', 5000.0, 1)"
        )
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) "
            "VALUES (2, '2026-02-02', -4000.0, 'cierre de la cuenta vieja')"
        )
        serie = balance_series(self.cur, months=6)
        por_mes = {p["month"]: p["balance"] for p in serie}
        self.assertEqual(por_mes["2026-02"], 1400.0)
        self.assertEqual(serie[-1]["balance"], total_balance(self.cur))


class TestBalanceSeriesConInversion(unittest.TestCase):
    """En la serie, una cuenta de inversión vale su valoración vigente en cada
    cierre de mes, no lo que se le ha aportado."""

    def setUp(self):
        self.con = _new_db()
        self.cur = self.con.cursor()
        self.cur.execute(
            "INSERT INTO accounts(id, name, initial_balance) VALUES (1, 'Banco', 1000.0)"
        )
        self.cur.execute(
            "INSERT INTO accounts(id, name, type, initial_balance) "
            "VALUES (2, 'Fondo', 'investment', 10000.0)"
        )
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) VALUES "
            "(1, '2026-01-10', -100.0, 'compra'),"
            "(1, '2026-02-15',  500.0, 'nómina')"
        )

    def tearDown(self):
        self.con.close()

    def test_sin_valoracion_el_fondo_aporta_lo_aportado(self):
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        self.assertEqual(por_mes["2026-01"], 10900.0)   # 900 + 10000
        self.assertEqual(por_mes["2026-02"], 11400.0)

    def test_cada_mes_toma_la_valoracion_vigente_en_su_cierre(self):
        self.cur.execute(
            "INSERT INTO account_valuations(account_id, date, value) VALUES "
            "(2, '2026-01-31', 10500.0),"
            "(2, '2026-02-28', 10800.0)"
        )
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        self.assertEqual(por_mes["2026-01"], 11400.0)   # 900 + 10500
        self.assertEqual(por_mes["2026-02"], 12200.0)   # 1400 + 10800

    def test_una_valoracion_posterior_alarga_la_serie(self):
        # El fondo se revaloriza en marzo aunque no haya ningún movimiento:
        # la curva tiene que llegar hasta ahí y recoger el cambio.
        self.cur.execute(
            "INSERT INTO account_valuations(account_id, date, value) "
            "VALUES (2, '2026-03-31', 11000.0)"
        )
        serie = balance_series(self.cur, months=6)
        self.assertEqual(serie[-1]["month"], "2026-03")
        self.assertEqual(serie[-1]["balance"], 12400.0)  # 1400 + 11000

    # Los tres casos de abajo cubren el tramo que se sacó del bucle de meses:
    # antes cada mes preguntaba a la base por cada cuenta de inversión, y ahora
    # se resuelve en memoria. Son las ramas donde eso podría torcerse.

    def test_lo_aportado_al_fondo_se_acumula_mes_a_mes(self):
        """Sin valoraciones, el fondo vale lo aportado HASTA ESE CIERRE, no lo
        aportado en total."""
        self.cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description) VALUES "
            "(2, '2026-01-20', 1000.0, 'aportación'),"
            "(2, '2026-02-20', 2000.0, 'aportación')"
        )
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        self.assertEqual(por_mes["2026-01"], 900.0 + 11000.0)
        self.assertEqual(por_mes["2026-02"], 1400.0 + 13000.0)

    def test_una_valoracion_a_mitad_de_mes_ya_cuenta_en_ese_cierre(self):
        self.cur.execute(
            "INSERT INTO account_valuations(account_id, date, value) "
            "VALUES (2, '2026-02-05', 10800.0)"
        )
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        self.assertEqual(por_mes["2026-01"], 900.0 + 10000.0, "enero es anterior")
        self.assertEqual(por_mes["2026-02"], 1400.0 + 10800.0)

    def test_dos_fondos_cada_uno_por_su_lado(self):
        """Uno valorado y otro no: el respaldo es por cuenta, no global."""
        self.cur.execute(
            "INSERT INTO accounts(id, name, type, initial_balance) "
            "VALUES (3, 'Fondo 2', 'investment', 2000.0)"
        )
        self.cur.execute(
            "INSERT INTO account_valuations(account_id, date, value) "
            "VALUES (2, '2026-01-31', 10500.0)"
        )
        por_mes = {p["month"]: p["balance"] for p in balance_series(self.cur, months=6)}
        # 900 del banco + 10500 declarados del fondo 1 + 2000 aportados al 2
        self.assertEqual(por_mes["2026-01"], 900.0 + 10500.0 + 2000.0)


if __name__ == "__main__":
    unittest.main()
