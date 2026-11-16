"""
Tests de la sección «Declaración de la Renta» (/renta), dentro de Configuración.

Lo que ve el usuario: el selector de ejercicio, el resumen, el detalle con su
total en cada concepto, el total de los dos seguros, la lista «por revisar»,
y los ajustes. Y lo que llega de fuera se valida en la puerta: un ejercicio
que no es un año cae en el de por defecto, y unos ajustes que no caben se
rechazan sin tocar lo guardado.

Datos inventados («Calle Ejemplo»). La base es temporal, pero `unittest
discover` comparte proceso: cada test limpia al entrar y al salir.
"""
import os
import re
import tempfile
import unittest
from datetime import date
from urllib.parse import parse_qs, unquote_plus, urlsplit

_TMP = tempfile.mkdtemp(prefix="tnt-renta-pantalla-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "renta-pantalla.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import renta  # noqa: E402
from app.services.categories import resolve_category  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")
INMUEBLE = "Calle Ejemplo"


class _Base(unittest.TestCase):
    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        with cursor() as cur:
            renta.cargar_ajustes(cur)
            self.cat = renta.guardar_ajustes(cur, INMUEBLE, ["TGR"]).categorias
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
            cuenta = cur.lastrowid
            impuestos = resolve_category(cur, "Impuestos y comisiones|Impuestos")
            movs = [
                ("2026-01-01", 820.00, self.cat["ingresos"], "Alquiler enero 26", None),
                ("2026-02-01", 820.00, self.cat["ingresos"], "Alquiler febrero 26", None),
                ("2026-02-04", -412.36, self.cat["impago"], "ASEGURADORA EJEMPLO", "Impago Calle Ejemplo"),
                ("2026-05-20", -158.41, self.cat["vivienda"], "CORREDURIA EJEMPLO", None),
                ("2026-01-05", -61.17, self.cat["ibi"], "Recibo Ayuntamiento", "IBI Calle Ejemplo"),
                ("2026-01-05", -142.80, self.cat["comunidad"], "Recibo C.P. CALLE EJEMPLO", None),
                ("2026-10-05", -61.17, impuestos, "Recibo Ayuntamiento", "IBI Calle Ejemplo"),
                ("2025-12-01", 900.00, self.cat["ingresos"], "Alquiler diciembre 25", None),
            ]
            for i, (fecha, imp, cat, desc, nota) in enumerate(movs):
                cur.execute(
                    "INSERT INTO transactions(account_id, date, amount, description, memo, "
                    "category_id, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cuenta, fecha, imp, desc, nota, cat, f"renta-pantalla-{i}"))

    def tearDown(self):
        self._vaciar()

    def _vaciar(self):
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    @staticmethod
    def _seccion(html: str, clave: str) -> str:
        """El bloque de un concepto: de su id a la hoja siguiente. Cortar en el
        siguiente concepto no vale: tras el último viene «por revisar»."""
        trozo = html.split(f'id="concepto-{clave}"', 1)[1]
        # «sheet» a secas o con más clases; «sheet-head» va dentro y no corta.
        return re.split(r'<div class="sheet[" ]', trozo, maxsplit=1)[0]


class TestPantalla(_Base):
    def test_responde_y_marca_su_seccion(self):
        r = client.get("/renta?ejercicio=2026")
        self.assertEqual(r.status_code, 200)
        subnav = r.text.split('class="subnav"', 1)[1].split("</nav>", 1)[0]
        self.assertRegex(subnav, r'href="/renta"\s+class="subnav-link is-active"')

    def test_el_selector_lista_los_ejercicios_y_marca_el_elegido(self):
        html = client.get("/renta?ejercicio=2025").text
        anios = re.findall(r'<option value="(\d{4})"', html)
        hoy = date.today().year
        for esperado in ("2026", "2025", str(hoy), str(hoy - 1)):
            self.assertIn(esperado, anios)
        self.assertRegex(html, r'<option value="2025" selected>')

    def test_el_resumen_y_el_total_de_seguros(self):
        html = client.get("/renta?ejercicio=2026").text
        resumen = html.split('id="resumen"', 1)[1].split("</table>", 1)[0]
        for concepto, total in (("Ingresos por alquiler", "1.640,00 €"), ("Seguro de impago", "412,36 €"),
                                ("Seguro de la vivienda", "158,41 €"), ("IBI", "61,17 €"),
                                ("Comunidad", "142,80 €")):
            with self.subTest(concepto=concepto):
                self.assertRegex(resumen, rf"{re.escape(concepto)}</t[dh]>\s*<td[^>]*>{re.escape(total)}")
        seguros = html.split('id="total-seguros"', 1)[1][:200]
        self.assertIn("570,77 €", seguros)

    def test_cada_concepto_tiene_su_detalle_y_su_total(self):
        html = client.get("/renta?ejercicio=2026").text
        for clave, filas, total in (("ingresos", 2, "1.640,00 €"), ("impago", 1, "412,36 €"),
                                    ("vivienda", 1, "158,41 €"), ("ibi", 1, "61,17 €"),
                                    ("comunidad", 1, "142,80 €")):
            with self.subTest(concepto=clave):
                bloque = self._seccion(html, clave)
                self.assertEqual(len(re.findall(r"<tr>\s*<td", bloque.split("<tbody>", 1)[1])), filas)
                self.assertIn(total, bloque.split("</tbody>", 1)[1])

    def test_cambiar_de_ejercicio_no_mezcla_movimientos(self):
        de_2026 = client.get("/renta?ejercicio=2026").text
        de_2025 = client.get("/renta?ejercicio=2025").text
        self.assertNotIn("Alquiler diciembre 25", de_2026)
        self.assertIn("Alquiler diciembre 25", de_2025)
        self.assertNotIn("Alquiler enero 26", de_2025)
        self.assertIn("900,00 €", self._seccion(de_2025, "ingresos"))

    def test_un_ejercicio_que_no_es_un_anio_cae_en_el_de_por_defecto(self):
        defecto = renta.ejercicio_por_defecto(date.today())
        for malo in ("abc", "1800", "99999", "2026.5", ""):
            with self.subTest(ejercicio=malo):
                r = client.get("/renta", params={"ejercicio": malo})
                self.assertEqual(r.status_code, 200)
                self.assertRegex(r.text, rf'<option value="{defecto}" selected>')

    def test_un_ejercicio_vacio_lo_dice(self):
        html = client.get("/renta?ejercicio=2019").text
        self.assertIn("No hay movimientos de 2019", html)
        self.assertRegex(html, r'<option value="2019" selected>')

    def test_enlaza_cada_concepto_con_movimientos_y_su_exportacion(self):
        html = client.get("/renta?ejercicio=2026").text
        for clave in ("ingresos", "impago", "vivienda", "ibi", "comunidad"):
            consulta = (f"category_id={self.cat[clave]}&amp;date_from=2026-01-01"
                        f"&amp;date_to=2026-12-31")
            with self.subTest(concepto=clave):
                bloque = self._seccion(html, clave)
                self.assertIn(f'href="/movimientos?{consulta}"', bloque)
                self.assertIn(f'href="/exportar.csv?{consulta}"', bloque)


class TestPorRevisar(_Base):
    def test_lista_lo_que_falta_y_enlaza_a_su_dia_sin_datos_personales(self):
        html = client.get("/renta?ejercicio=2026").text
        lista = html.split('id="por-revisar"', 1)[1]
        self.assertIn("05/10/2026", lista)
        self.assertIn('href="/movimientos?date_from=2026-10-05&amp;date_to=2026-10-05"', lista)
        for enlace in re.findall(r'href="([^"]+)"', lista):
            self.assertNotIn("Ejemplo", unquote_plus(enlace))


class TestAjustes(_Base):
    def _guardar(self, **campos):
        datos = {"inmueble": INMUEBLE, "ignorar": "TGR, Basuras", "ejercicio": "2026"}
        datos.update(campos)
        r = client.post("/renta/ajustes", data=datos, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        destino = urlsplit(r.headers["location"])
        return destino, parse_qs(destino.query)

    def test_guardar_vuelve_al_ejercicio_sin_el_nombre_del_piso_en_la_url(self):
        destino, qs = self._guardar(inmueble="Otra Calle")
        self.assertEqual(destino.path, "/renta")
        self.assertEqual(qs["ejercicio"], ["2026"])
        self.assertIn("msg", qs)
        self.assertNotIn("Calle", unquote_plus(destino.query))
        with cursor() as cur:
            aj = renta.cargar_ajustes(cur)
        self.assertEqual((aj.inmueble, aj.ignorar), ("Otra Calle", ("TGR", "Basuras")))

    def test_rechaza_lo_que_no_cabe_sin_tocar_lo_guardado(self):
        for campos in ({"inmueble": "x" * 81}, {"ignorar": "y" * 41},
                       {"ignorar": ", ".join(f"p{i}" for i in range(21))}):
            with self.subTest(campos=list(campos)):
                _, qs = self._guardar(**campos)
                self.assertIn("err", qs)
        with cursor() as cur:
            aj = renta.cargar_ajustes(cur)
        self.assertEqual((aj.inmueble, aj.ignorar), (INMUEBLE, ("TGR",)))


class TestCategoriaBorrada(_Base):
    def test_avisa_y_se_repara(self):
        with cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = ?", (self.cat["ibi"],))
        html = client.get("/renta?ejercicio=2026").text
        self.assertIn("Falta la categoría", self._seccion(html, "ibi"))
        self.assertIn('action="/renta/categorias"', html)
        r = client.post("/renta/categorias", data={"ejercicio": "2026"}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertNotIn("Falta la categoría", client.get("/renta?ejercicio=2026").text)


if __name__ == "__main__":
    unittest.main()
