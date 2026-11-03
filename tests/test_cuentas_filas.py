"""
Tests de la lista de Cuentas con filas de dos líneas (design-system.md,
referencia 3): el nombre arriba y, debajo, un subtítulo que no repite lo que ya
dice el nombre; el saldo, a la derecha. Las columnas de banco e IBAN desaparecen:
el IBAN completo se ve al editar la cuenta.

Datos inventados. La base es temporal, pero `unittest discover` comparte proceso
con otros ficheros: cada test limpia al entrar y al salir.
"""
import os
import re
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-cuentas-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "cuentas.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.accounts import subtitulo_cuenta  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class TestSubtitulo(unittest.TestCase):
    def test_banco_y_ultimos_digitos(self):
        self.assertEqual(subtitulo_cuenta("Cuenta nómina", "Banco Ejemplo", "ES00 0000 0000 0000 0000 1234", "bank"),
                         "Banco Ejemplo · ····1234")

    def test_no_repite_el_banco_que_ya_dice_el_nombre(self):
        self.assertEqual(subtitulo_cuenta("Banco Ejemplo", "Banco Ejemplo", "ES0000000000000000005678", "bank"),
                         "····5678")

    def test_si_el_nombre_lo_dice_todo_queda_el_tipo(self):
        self.assertEqual(subtitulo_cuenta("Ejemplo ****4321", "Ejemplo", "ES0000000000000000004321", "bank"),
                         "Cuenta bancaria")

    def test_el_tipo_cuando_no_es_de_banco(self):
        self.assertEqual(subtitulo_cuenta("Fondo indexado", "Gestora", None, "investment"), "Gestora · Inversión")
        self.assertEqual(subtitulo_cuenta("Gestora Capital", "Gestora Capital", "", "investment"), "Inversión")

    def test_el_banco_se_busca_por_palabra_entera(self):
        # «ING» no está en «Parking»: el subtítulo tiene que decirlo.
        self.assertEqual(subtitulo_cuenta("Hucha parking", "ING", "ES0000000000000000009999", "bank"),
                         "ING · ····9999")


class TestListaDeCuentas(unittest.TestCase):
    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, bank, iban, type, initial_balance) "
                        "VALUES ('Cuenta nómina', 'Banco Ejemplo', 'ES0000000000000000001234', 'bank', 100)")

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    def test_la_fila_lleva_nombre_y_subtitulo(self):
        html = client.get("/cuentas").text
        fila = re.search(r"<tbody>(.*?)</tr>", html, re.S).group(1)
        self.assertIn("Cuenta nómina", fila)
        self.assertIn("Banco Ejemplo · ····1234", fila)

    def test_ya_no_hay_columnas_de_banco_ni_de_iban(self):
        cabecera = re.search(r"<thead>(.*?)</thead>", client.get("/cuentas").text, re.S).group(1)
        self.assertNotIn("IBAN", cabecera)
        self.assertNotIn("Banco / Tipo", cabecera)
        self.assertIn("Cuenta", cabecera)

    def test_en_el_movil_se_ocultan_las_secundarias_y_no_el_saldo(self):
        # Bajo 640px, .col-secundaria se oculta: el saldo actual tiene que quedar
        # a la vista junto al nombre, antes que el saldo inicial y los movimientos.
        cabecera = re.search(r"<thead>(.*?)</thead>", client.get("/cuentas").text, re.S).group(1)
        celdas = dict((" ".join(re.sub(r"<[^>]+>", "", c).split()), cls)
                      for cls, c in re.findall(r'<th(?: class="([^"]*)")?>(.*?)</th>', cabecera, re.S))
        self.assertIn("col-secundaria", celdas["Saldo inicial"])
        self.assertIn("col-secundaria", celdas["Movs."])
        self.assertNotIn("col-secundaria", celdas["Saldo actual"])


if __name__ == "__main__":
    unittest.main()
