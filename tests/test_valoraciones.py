"""
Tests del formulario de valoración de las cuentas de inversión.

El informe del fondo llega con el mes ya cerrado: el de septiembre, a primeros
de octubre. El formulario proponía la fecha de hoy, así que la valoración de
septiembre se guardó el 01/10 y la curva del panel enseñaba la subida de
septiembre como si fuera de octubre. Ahora propone el último día del mes
anterior, y al guardar dice qué fecha ha quedado, que es lo que faltaba para
darse cuenta.

La conciliación de Cuentas, en cambio, sigue proponiendo hoy: se concilia
contra el saldo que dice el banco hoy. Un test lo vigila para que nadie
«arregle» las dos a la vez.

La base es temporal y propia, pero `unittest discover` comparte proceso con
otros ficheros: por eso cada test limpia al entrar y al salir.
"""
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from urllib.parse import parse_qs, unquote_plus, urlsplit

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-valoraciones-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "valoraciones.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


def _cierre_del_mes_anterior(hoy: date) -> date:
    """Calculado aquí a mano, sin la función de la app, para no probarla consigo misma."""
    return hoy.replace(day=1) - timedelta(days=1)


class _Base(unittest.TestCase):
    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, type, initial_balance) "
                        "VALUES ('Fondo de prueba', 'investment', 50000)")
            self.fondo = cur.lastrowid

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM account_valuations")
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    @staticmethod
    def _valoraciones():
        with cursor() as cur:
            return [dict(r) for r in cur.execute(
                "SELECT date, value FROM account_valuations ORDER BY date")]

    def _guardar(self, **campos):
        datos = {"date": "2026-09-30", "value": "63759.24", "note": ""}
        datos.update(campos)
        r = client.post(f"/cuentas/{self.fondo}/valoracion", data=datos,
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        destino = urlsplit(r.headers["location"])
        return destino.path, parse_qs(destino.query)


class TestFechaPropuesta(_Base):
    def test_el_formulario_propone_el_cierre_del_mes_anterior(self):
        html = client.get("/inversiones").text
        m = re.search(rf'id="val-date-{self.fondo}"[^>]*value="([^"]+)"', html, re.S)
        self.assertIsNotNone(m, "no aparece el campo de fecha del formulario")
        propuesta = date.fromisoformat(m.group(1))
        self.assertEqual(propuesta, _cierre_del_mes_anterior(date.today()))
        # Y no es hoy: ese era el fallo.
        self.assertNotEqual(propuesta, date.today())

    def test_la_conciliacion_sigue_proponiendo_hoy(self):
        html = client.get("/cuentas").text
        m = re.search(r'id="reconcile-\d+".*?name="date"\s+value="([^"]+)"', html, re.S)
        self.assertIsNotNone(m, "no aparece el diálogo de conciliación")
        self.assertEqual(m.group(1), date.today().isoformat())


class TestGuardar(_Base):
    def test_guardar_vuelve_a_inversiones_diciendo_la_fecha(self):
        ruta, qs = self._guardar()
        self.assertEqual(ruta, "/inversiones")
        self.assertIn("30/09/2026", qs["msg"][0])
        self.assertEqual(self._valoraciones(), [{"date": "2026-09-30", "value": 63759.24}])

    def test_el_importe_no_viaja_en_la_url(self):
        # El aviso va en la query string, y la URL acaba en el historial del
        # navegador, que puede sincronizarse fuera de esta máquina. La fecha
        # basta para ver el error; la cifra ya sale en la tarjeta del fondo.
        r = client.post(f"/cuentas/{self.fondo}/valoracion",
                        data={"date": "2026-09-30", "value": "63759.24", "note": ""},
                        follow_redirects=False)
        destino = unquote_plus(r.headers["location"])
        for forma in ("63759", "63.759", "63,759"):
            with self.subTest(forma=forma):
                self.assertNotIn(forma, destino)

    def test_el_aviso_se_ve_en_la_pagina(self):
        _, qs = self._guardar()
        html = client.get("/inversiones", params={"msg": qs["msg"][0]}).text
        self.assertIn("30/09/2026", html)

    def test_misma_fecha_sustituye_la_cifra(self):
        # Corregir una cifra mal tecleada sin tener que borrarla antes.
        self._guardar(value="63000")
        self._guardar(value="63759.24")
        self.assertEqual(self._valoraciones(), [{"date": "2026-09-30", "value": 63759.24}])

    def test_rechaza_fecha_imposible(self):
        for mala in ("2026-13-01", "2026-02-30", "30/09/2026", "ayer", " "):
            with self.subTest(fecha=mala):
                ruta, qs = self._guardar(date=mala)
                self.assertEqual(ruta, "/inversiones")
                self.assertIn("err", qs)
        self.assertEqual(self._valoraciones(), [])

    def test_rechaza_valor_negativo_o_no_finito(self):
        for malo in ("-1", "nan", "inf"):
            with self.subTest(valor=malo):
                ruta, qs = self._guardar(value=malo)
                self.assertIn("err", qs)
        self.assertEqual(self._valoraciones(), [])

    def test_acepta_valor_cero(self):
        # Un fondo vaciado del todo vale cero, y eso es un dato, no un error.
        _, qs = self._guardar(value="0")
        self.assertIn("msg", qs)

    def test_borrar_vuelve_a_inversiones(self):
        self._guardar()
        with cursor() as cur:
            vid = cur.execute("SELECT id FROM account_valuations").fetchone()["id"]
        r = client.post(f"/cuentas/valoracion/{vid}/borrar", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(urlsplit(r.headers["location"]).path, "/inversiones")
        self.assertEqual(self._valoraciones(), [])



class TestCifrasDelFondo(_Base):
    """Las tres cifras de cada fondo llevan los céntimos en voladita, como las del
    panel (design-system.md, referencia 3). El texto que se lee no cambia."""

    def test_las_tres_cifras_llevan_los_centimos_aparte(self):
        with cursor() as cur:
            cur.execute("INSERT INTO account_valuations(account_id, date, value) "
                        "VALUES (?, '2026-01-31', 51234.56)", (self.fondo,))
        valores = re.findall(r'<div class="kpi-value[^"]*">(.*?)</div>', client.get("/inversiones").text, re.S)
        self.assertEqual(len(valores), 3)
        for v in valores:
            self.assertIn('class="cifra-cts"', v)
        textos = [" ".join(re.sub(r"<[^>]+>", "", v).split()) for v in valores]
        self.assertEqual(textos, ["50.000,00 €", "51.234,56 €", "+1.234,56 €"])

    def test_sin_valoracion_el_valor_es_una_raya(self):
        valores = re.findall(r'<div class="kpi-value[^"]*">(.*?)</div>', client.get("/inversiones").text, re.S)
        self.assertEqual(" ".join(valores[1].split()), "—")


if __name__ == "__main__":
    unittest.main()
