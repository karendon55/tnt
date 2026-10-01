"""
Tests de las variaciones mensuales del panel (ingresos y gastos).

Los gastos llegan de month_income_expense en negativo: son la suma de los
importes de salida. Restados tal cual, un mes que gasta MÁS da una variación
NEGATIVA (−7.963 − (−3.992) = −3.971), y el panel la pintaba como un descenso
en verde. Pasó de verdad en septiembre de 2026: el gasto casi se duplicó y el
panel decía «▼ 99,5 %».

La base es temporal y propia, pero `unittest discover` comparte proceso con
otros ficheros que también la usan: por eso cada test limpia al entrar y al
salir, para no dejar movimientos a los que esperan una base vacía.
"""
import os
import re
import tempfile
import unittest

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-variaciones-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "variaciones.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.dashboard import _variacion_pct  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class TestVariacionPct(unittest.TestCase):
    def test_gasto_que_sube_es_variacion_positiva(self):
        # El caso real: 3.991,98 € en agosto, 7.963,73 € en septiembre.
        self.assertEqual(_variacion_pct(-7963.73, -3991.98), 99.5)

    def test_gasto_que_baja_es_variacion_negativa(self):
        self.assertEqual(_variacion_pct(-2000.0, -4000.0), -50.0)

    def test_ingreso_que_sube(self):
        self.assertEqual(_variacion_pct(8106.06, 7600.38), 6.7)

    def test_mes_sin_cambio(self):
        self.assertEqual(_variacion_pct(-500.0, -500.0), 0.0)

    def test_mes_que_cae_a_cero(self):
        self.assertEqual(_variacion_pct(0.0, -500.0), -100.0)

    def test_sin_mes_de_referencia_no_hay_variacion(self):
        # Dividir entre cero no puede dar un porcentaje: mejor ninguno.
        self.assertIsNone(_variacion_pct(-500.0, 0.0))
        self.assertIsNone(_variacion_pct(-500.0, None))


class TestPanelMuestraElSentidoCorrecto(unittest.TestCase):
    """De extremo a extremo: lo que de verdad ve el usuario en el panel."""

    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
            cuenta = cur.lastrowid
            movimientos = [
                ("2026-08-10", -3991.98, "Gastos de agosto"),
                ("2026-09-10", -7963.73, "Gastos de septiembre"),
            ]
            for i, (fecha, importe, desc) in enumerate(movimientos):
                cur.execute(
                    "INSERT INTO transactions(account_id, date, amount, description, hash) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cuenta, fecha, importe, desc, f"variacion-{i}"),
                )

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    @staticmethod
    def _variacion_mostrada(html, etiqueta):
        """(clases, texto) de la línea de variación bajo el KPI indicado."""
        bloque = html.split(etiqueta, 1)[1]
        m = re.search(r'class="kpi-delta ([^"]*)">\s*(.*?)\s*</div>', bloque, re.S)
        return m.group(1), m.group(2)

    def test_gasto_que_casi_se_duplica_sale_al_alza_y_en_rojo(self):
        r = client.get("/?month=2026-09")
        self.assertEqual(r.status_code, 200)
        clases, texto = self._variacion_mostrada(r.text, "Gastos del mes")
        self.assertIn("▲", texto)
        self.assertNotIn("▼", texto)
        self.assertIn("99,5", texto)
        # Gastar más es mala noticia: rojo, no verde.
        self.assertIn("is-negative", clases)
        self.assertNotIn("is-positive", clases)

    def test_gasto_que_baja_sale_a_la_baja_y_en_verde(self):
        # Mismo dato al revés: en agosto se gastó menos que en septiembre.
        with cursor() as cur:
            cur.execute("UPDATE transactions SET date = '2026-07-10' WHERE hash = 'variacion-1'")
        # julio −7.963,73 → agosto −3.991,98: el gasto cae casi a la mitad
        clases, texto = self._variacion_mostrada(
            client.get("/?month=2026-08").text, "Gastos del mes")
        self.assertIn("▼", texto)
        self.assertIn("49,9", texto)
        self.assertIn("is-positive", clases)


if __name__ == "__main__":
    unittest.main()
