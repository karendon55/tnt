"""
Las pantallas de TNT en un móvil (375 px).

Ninguna página puede desplazarse de lado: se comprueba midiendo en un
navegador real que `scrollWidth` no pase de `clientWidth`. Un navegador no
cabe en estos tests, así que aquí se fija cada pieza que lo consigue, para que
no se pierda ninguna.

El panel medía 598 px. Por debajo de 1000 px, «Últimos movimientos» y su
lateral (`.sheet-mov`) pasan a una sola pista `1fr`, que no baja del ancho
mínimo de su contenido, y la tabla pedía 574 px: era automática, con topes de
240 y 170 px en descripción y categoría. Ahora la pista es `minmax(0,…)`, la
tabla es `table-fixed` (el texto se recorta con puntos suspensivos) y, en el
móvil, la categoría se oculta: con cuatro columnas en 327 px la descripción
quedaba en nada.

Backup medía 607 px: la fila de la base ponía en línea la ruta, que no tiene
espacios por donde partirse, y dos píldoras que quedaban fuera. Alias (551 px)
y Lotes de importación (996 px) tenían tablas sin su contenedor con scroll, y
sus celdas no parten línea.

Y la barra de arriba ocupaba 216 px fijos: los seis enlaces, apretados entre la
marca y el botón de tema, se partían en cuatro filas. En el móvil van en su
propia fila, debajo, y la barra deja de ser fija; en el escritorio no cambia.

La base es temporal y propia, pero `unittest discover` comparte proceso con
otros ficheros: cada test limpia al entrar y al salir.
"""
import json
import os
import re
import tempfile
import unittest

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-movil-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "movil.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import STATIC_DIR  # noqa: E402
from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

ANCHO_MOVIL = 375

# Un @media(max-width:N){…} con sus reglas dentro (un nivel de anidamiento).
_MEDIA = re.compile(
    r"@media\s*\(\s*max-width\s*:\s*(\d+)px\s*\)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}")


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
    for tope, cuerpo in _MEDIA.findall(css):
        if int(tope) >= ancho:
            fuera.extend(_reglas(cuerpo))
    return fuera


def _reglas_de_escritorio(css: str) -> list[tuple[str, str]]:
    """Las reglas que no están dentro de ningún @media(max-width)."""
    return _reglas(_MEDIA.sub("", css))


def _tabla_tras(html: str, marca: str) -> tuple[str, str]:
    """(la etiqueta justo antes, la tabla) de la primera tabla tras `marca`."""
    bloque = html.split(marca, 1)[1]
    antes, resto = bloque.split("<table", 1)
    tabla = "<table" + resto.split("</table>", 1)[0] + "</table>"
    return antes.rstrip().rsplit("\n", 1)[-1].strip(), tabla


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
        envoltorio, tabla = _tabla_tras(client.get("/").text, "Últimos movimientos")
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
        _, tabla = _tabla_tras(client.get("/").text, "Últimos movimientos")
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


class TestPantallasDeConfiguracionEnElMovil(unittest.TestCase):
    """Backup, Alias y Lotes de importación."""

    RUTA_LARGA = "/home/alguien/Documentos/una/ruta/de/backup/bastante/larga/sin/espacios"

    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("INSERT INTO description_aliases(pattern, alias) "
                        "VALUES ('BARCO COMPRA EN DEMARY FRUTERIAS S.L.', 'Demary Frutería')")
            cur.execute(
                "INSERT INTO import_batches(files, inserted, duplicates) VALUES (?, 1, 0)",
                (json.dumps([{"filename": "movements-01102026.xls", "bank": "ING",
                              "account": "Cuenta naranja", "inserted": 1,
                              "duplicates": 0}]),))
            cur.execute("INSERT INTO settings(key, value) VALUES ('backup_destinations', ?)",
                        (json.dumps([{"path": self.RUTA_LARGA, "mode": "plain"}]),))

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM description_aliases")
            cur.execute("DELETE FROM import_batches")
            cur.execute("DELETE FROM settings WHERE key = 'backup_destinations'")

    def test_alias_la_tabla_se_desliza_en_su_caja(self):
        envoltorio, _ = _tabla_tras(client.get("/alias").text, "<main")
        self.assertEqual(envoltorio, '<div class="table-scroll">')

    def test_lotes_la_tabla_se_desliza_en_su_caja(self):
        envoltorio, _ = _tabla_tras(client.get("/importar/lotes").text, "<main")
        self.assertEqual(envoltorio, '<div class="table-scroll">')

    def test_backup_la_fila_de_la_base_parte_linea(self):
        html = client.get("/backup").text
        m = re.search(r'<div class="([^"]*)">\s*<span class="muted small">Base de datos actual'
                      r'</span>\s*<span class="([^"]*)">', html)
        self.assertIsNotNone(m, "no aparece la fila de la base de datos")
        self.assertIn("wrap-w", m.group(1).split(), "la fila no parte línea")
        self.assertIn("break-any", m.group(2).split(), "la ruta de la base no se parte")

    def test_backup_las_rutas_de_destino_se_parten(self):
        html = client.get("/backup").text
        clases = re.findall(rf'<span class="([^"]*)">{re.escape(self.RUTA_LARGA)}</span>', html)
        # Sale dos veces: en la lista de destinos y en su configuración.
        self.assertEqual(len(clases), 2)
        for c in clases:
            with self.subTest(clases=c):
                self.assertIn("break-any", c.split())

    def test_la_utilidad_parte_donde_haga_falta(self):
        reglas = [d for s, d in _reglas(_css()) if s == ".break-any"]
        self.assertTrue(reglas, "no existe .break-any")
        self.assertRegex(reglas[0], r"overflow-wrap\s*:\s*anywhere")


class TestBarraEnElMovil(unittest.TestCase):
    def test_deja_de_ser_fija(self):
        sueltas = [s for s, d in _reglas_bajo(_css(), ANCHO_MOVIL)
                   if ".topbar" in s and re.search(r"position\s*:\s*static", d)]
        self.assertTrue(sueltas, f"a {ANCHO_MOVIL} px la barra sigue fija")

    def test_los_enlaces_van_en_su_propia_fila(self):
        fila = [s for s, d in _reglas_bajo(_css(), ANCHO_MOVIL)
                if re.search(r"\.nav(?![\w-])", s) and re.search(r"flex-basis\s*:\s*100%", d)]
        self.assertTrue(fila, f"a {ANCHO_MOVIL} px los enlaces siguen apretados junto a la marca")

    def test_en_el_escritorio_sigue_fija(self):
        fija = [s for s, d in _reglas_de_escritorio(_css())
                if s == ".topbar" and re.search(r"position\s*:\s*sticky", d)]
        self.assertTrue(fija, "en el escritorio la barra tiene que seguir fija")


if __name__ == "__main__":
    unittest.main()
