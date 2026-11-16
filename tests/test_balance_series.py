"""
Tests de la curva del panel: el patrimonio al cierre de cada mes.
"""
import unittest

from app.services.balances import balance_series, total_balance
from tests.bd_minima import nueva_bd


class TestBalanceSeries(unittest.TestCase):
    """La serie del panel: saldo acumulado al cierre de cada mes.

    Regresión: la serie se construía hasta el mes actual del calendario y
    luego cortaba los últimos N meses, así que con extractos atrasados la
    ventana se llenaba de meses arrastrados y devolvía una recta.
    """

    def setUp(self):
        self.con = nueva_bd()
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
        con = nueva_bd()
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
        self.con = nueva_bd()
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
