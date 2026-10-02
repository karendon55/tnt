"""
Tests de la línea que va bajo el patrimonio total en el panel.

Decía «▲ … este mes» con el neto del mes: ingresos menos gastos. Pero el
patrimonio también se mueve con lo que gana o pierde el fondo, que no es
ingreso, así que la cifra no cuadraba con la curva de saldo. En septiembre de
2026 decía 4.539,12 € y el patrimonio había subido 4.964,10 €: faltaban los
424,98 € del fondo. Y el neto ya tiene su propia tarjeta justo debajo.

Ahora es el patrimonio al cierre del mes que se ve menos el del cierre del
anterior, y nombra ese mes: «este mes» tampoco era verdad cuando el panel cae
al último mes con datos, ni cuando se elige otro.

Los datos son de 2024 para que «el último mes con datos» no dependa del día
en que se pasen los tests. La base es temporal y propia, pero `unittest
discover` comparte proceso con otros ficheros: cada test limpia al entrar y al
salir.
"""
import json
import os
import re
import tempfile
import unittest

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-patrimonio-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "patrimonio.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

# Cierres del patrimonio (cuenta + fondo):
#   junio 1.000 + 10.000 (sin valorar: lo aportado)      = 11.000
#   julio 2.200 + 10.100                                 = 12.300
#   agosto 1.700 + 10.200  → −400 (neto −500, fondo +100) = 11.900
#   septiembre 3.200 + 10.500 → +1.800 (neto +1.500, fondo +300) = 13.700
_MOVIMIENTOS = [
    ("2024-07-05", 2000.0, "Nómina julio"),
    ("2024-07-20", -800.0, "Gastos julio"),
    ("2024-08-05", 2000.0, "Nómina agosto"),
    ("2024-08-20", -2500.0, "Gastos agosto"),
    ("2024-09-05", 3000.0, "Nómina septiembre"),
    ("2024-09-20", -1500.0, "Gastos septiembre"),
]
_VALORACIONES = [("2024-07-31", 10100.0), ("2024-08-31", 10200.0), ("2024-09-30", 10500.0)]


def _linea_del_patrimonio(html: str) -> tuple[str, str]:
    """(clase, texto) de la línea bajo la cifra del patrimonio."""
    hero = re.search(r'<section class="hero">(.*?)</section>', html, re.S).group(1)
    m = re.search(r'<span class="([^"]*)">\s*(.*?)\s*</span>', hero, re.S)
    return m.group(1), " ".join(m.group(2).split())


def _importe(texto: str) -> float:
    """'▲ 1.800,00 € en …' → 1800.0"""
    cifra = re.search(r"([\d.]+,\d{2}) €", texto).group(1)
    return float(cifra.replace(".", "").replace(",", "."))


class TestLineaDelPatrimonio(unittest.TestCase):
    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, type, initial_balance) "
                        "VALUES ('Cuenta', 'bank', 1000)")
            cuenta = cur.lastrowid
            cur.execute("INSERT INTO accounts(name, type, initial_balance) "
                        "VALUES ('Fondo', 'investment', 10000)")
            fondo = cur.lastrowid
            for i, (fecha, importe, desc) in enumerate(_MOVIMIENTOS):
                cur.execute(
                    "INSERT INTO transactions(account_id, date, amount, description, hash) "
                    "VALUES (?, ?, ?, ?, ?)", (cuenta, fecha, importe, desc, f"patrimonio-{i}"))
            for fecha, valor in _VALORACIONES:
                cur.execute("INSERT INTO account_valuations(account_id, date, value) "
                            "VALUES (?, ?, ?)", (fondo, fecha, valor))

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM account_valuations")
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    def test_cuenta_lo_que_gana_el_fondo(self):
        clase, texto = _linea_del_patrimonio(client.get("/?month=2024-09").text)
        self.assertIn("▲", texto)
        self.assertIn("1.800,00 €", texto)
        # El neto del mes, 1.500, era la cifra de antes.
        self.assertNotIn("1.500,00", texto)
        self.assertIn("amount-pos", clase)

    def test_el_neto_sigue_en_su_tarjeta(self):
        html = client.get("/?month=2024-09").text
        tarjeta = html.split("Neto del mes", 1)[1][:300]
        self.assertIn("+1.500,00 €", tarjeta)

    def test_una_bajada_sale_a_la_baja_y_en_rojo(self):
        # Agosto: se gastó 500 más de lo que entró y el fondo ganó 100.
        clase, texto = _linea_del_patrimonio(client.get("/?month=2024-08").text)
        self.assertIn("▼", texto)
        self.assertIn("400,00 €", texto)
        self.assertIn("amount-neg", clase)

    def test_nombra_el_mes_elegido(self):
        _, texto = _linea_del_patrimonio(client.get("/?month=2024-08").text)
        self.assertIn("agosto 2024", texto)
        self.assertNotIn("este mes", texto)

    def test_al_caer_al_ultimo_mes_con_datos_nombra_ese_mes(self):
        # Sin ?month y sin datos en el mes en curso, el panel enseña el último
        # con datos. «Este mes» sería el de hoy, que no es el que se ve.
        _, texto = _linea_del_patrimonio(client.get("/").text)
        self.assertIn("septiembre 2024", texto)
        self.assertIn("1.800,00 €", texto)
        self.assertNotIn("este mes", texto)

    def test_cuadra_con_la_curva_del_saldo(self):
        # Lo que no cuadraba: la curva subía más que la cifra de arriba.
        html = client.get("/").text
        curva = json.loads(re.search(r"const lineData = (\{.*?\});", html).group(1))
        subida = round(curva["values"][-1] - curva["values"][-2], 2)
        _, texto = _linea_del_patrimonio(html)
        self.assertEqual(_importe(texto), subida)

    def test_un_mes_sin_cambios_sale_neutro(self):
        # Octubre no tiene movimientos ni valoraciones: ni sube ni baja, y
        # un «▲ 0,00 €» en verde diría que algo fue bien.
        clase, texto = _linea_del_patrimonio(client.get("/?month=2024-10").text)
        self.assertNotIn("▲", texto)
        self.assertNotIn("▼", texto)
        self.assertIn("Sin cambios en octubre 2024", texto)
        self.assertNotIn("amount-pos", clase)
        self.assertNotIn("amount-neg", clase)


if __name__ == "__main__":
    unittest.main()
