"""
El panel en la pantalla de un móvil.

A 375 px la página se desplazaba de lado: medía 598 px. Por debajo de 1000 px,
«Últimos movimientos» y su lateral (`.sheet-mov`) pasan a una sola columna
`1fr`, y una pista `1fr` no baja del ancho mínimo de su contenido. La tabla
pedía 574 px: era automática, con topes de 240 y 170 px en descripción y
categoría, y esas celdas no parten el texto.

Tres piezas lo arreglan, y cada test fija una para que no se pierda:
la pista es `minmax(0,…)`, la tabla es `table-fixed` (las columnas obedecen a
las cabeceras y el texto se recorta con puntos suspensivos) y, en pantallas de
móvil, la categoría se oculta: con cuatro columnas en 327 px la descripción
quedaba en nada. Un navegador no cabe en estos tests; la prueba de verdad es
medir a 375 px que `scrollWidth` no pase de `clientWidth`.

La base es temporal y propia, pero `unittest discover` comparte proceso con
otros ficheros: cada test limpia al entrar y al salir.
"""
import os
import re
import tempfile
import unittest

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-panel-movil-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "panel-movil.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import STATIC_DIR  # noqa: E402
from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

ANCHO_MOVIL = 375


def _css() -> str:
    """Las cinco hojas juntas y sin comentarios, que pueden llevar llaves."""
    texto = "\n".join(p.read_text(encoding="utf-8")
                      for p in sorted((STATIC_DIR / "css").glob("*.css")))
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _reglas(css: str) -> list[tuple[str, str]]:
    """(selector, declaraciones) de cada bloque que no tiene bloques dentro."""
    return [(s.strip(), d) for s, d in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def _reglas_bajo(css: str, ancho: int) -> list[tuple[str, str]]:
    """Las reglas que aplican a una pantalla de `ancho` px por estar dentro de
    un @media(max-width:N) con N igual o mayor."""
    fuera = []
    for tope, cuerpo in re.findall(
            r"@media\s*\(\s*max-width\s*:\s*(\d+)px\s*\)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", css):
        if int(tope) >= ancho:
            fuera.extend(_reglas(cuerpo))
    return fuera


class TestPanelEnElMovil(unittest.TestCase):
    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
            cuenta = cur.lastrowid
            for i in range(3):
                cur.execute(
                    "INSERT INTO transactions(account_id, date, amount, description, hash) "
                    "VALUES (?, '2024-09-10', -12.5, 'Pago en PANISHOP MADRID ES', ?)",
                    (cuenta, f"movil-{i}"))

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    @staticmethod
    def _tabla_de_ultimos(html: str) -> tuple[str, str]:
        """(la etiqueta justo antes de la tabla, la tabla) de «Últimos movimientos»."""
        bloque = html.split("Últimos movimientos", 1)[1]
        antes, resto = bloque.split("<table", 1)
        tabla = "<table" + resto.split("</table>", 1)[0] + "</table>"
        return antes.rstrip().rsplit("\n", 1)[-1].strip(), tabla

    def test_las_pistas_de_la_rejilla_pueden_estrecharse(self):
        valores = [v for sel, decl in _reglas(_css()) if ".sheet-mov" in sel
                   for v in re.findall(r"grid-template-columns\s*:([^;]+)", decl)]
        self.assertTrue(valores, "no se encontró la rejilla de .sheet-mov")
        for v in valores:
            with self.subTest(pistas=v):
                sueltas = re.sub(r"minmax\(\s*0\s*,\s*[\d.]+fr\s*\)", "", v)
                self.assertNotRegex(
                    sueltas, r"[\d.]+fr",
                    "una pista fr sin minmax(0,…) no baja del mínimo de su contenido")

    def test_la_tabla_recorta_en_vez_de_empujar(self):
        envoltorio, tabla = self._tabla_de_ultimos(client.get("/").text)
        self.assertEqual(envoltorio, '<div class="table-scroll">',
                         "la tabla no va dentro de su contenedor con scroll")
        clases = re.search(r'<table class="([^"]*)"', tabla).group(1).split()
        self.assertIn("table-fixed", clases)
        # Descripción y categoría se recortan: con table-fixed, .trunc obedece
        # al ancho de la columna en vez de imponer el del texto.
        filas = re.findall(r"<tr>(.*?)</tr>", tabla.split("<tbody>", 1)[1], re.S)
        self.assertEqual(len(filas), 3)
        for fila in filas:
            celdas = re.findall(r'<td class="([^"]*)"', fila)
            self.assertIn("trunc", celdas[1].split(), "la descripción no se recorta")
            self.assertIn("trunc", celdas[2].split(), "la categoría no se recorta")

    def test_la_categoria_se_oculta_en_el_movil(self):
        _, tabla = self._tabla_de_ultimos(client.get("/").text)
        clases_tabla = set(re.search(r'<table class="([^"]*)"', tabla).group(1).split())
        # La cabecera y cada celda de la columna llevan la misma marca...
        cabecera = re.search(r'<th class="([^"]*)">Categoría</th>', tabla)
        self.assertIsNotNone(cabecera, "la cabecera de la categoría no lleva clase")
        marca = set(cabecera.group(1).split())
        filas = re.findall(r"<tr>(.*?)</tr>", tabla.split("<tbody>", 1)[1], re.S)
        for fila in filas:
            tercera = re.findall(r'<td class="([^"]*)"', fila)[2]
            self.assertTrue(marca & set(tercera.split()),
                            "una celda de la categoría no lleva la marca de su cabecera")
        # ...y a ancho de móvil hay una regla que las quita a todas.
        ocultas = [sel for sel, decl in _reglas_bajo(_css(), ANCHO_MOVIL)
                   if re.search(r"display\s*:\s*none", decl)
                   and any(f".{c}" in sel for c in clases_tabla)
                   and any(f".{c}" in sel for c in marca)]
        self.assertTrue(ocultas, f"a {ANCHO_MOVIL} px nada oculta la columna de la categoría")


if __name__ == "__main__":
    unittest.main()
