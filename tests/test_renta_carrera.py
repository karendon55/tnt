"""
Tests de la primera vez que se abre la Renta, con dos peticiones a la vez.

La Renta crea sus categorías («Inmueble alquilado» y sus hijas) la primera vez
que se abre. Con dos peticiones a la vez, las dos veían que faltaban y las dos
intentaban crearlas. En modo WAL la segunda no llegaba a duplicarlas: fallaba
con «database is locked», porque trabajaba con una foto vieja de la base, y se
veía una página de error. Ahora:

- la creación pide la escritura desde el principio (`cursor(inmediata=True)`):
  la otra petición espera, y luego ve las categorías ya hechas;
- un índice único impide dos categorías principales con el mismo nombre,
  vengan de donde vengan, y `resolve_category` reutiliza la que ya está.

Datos inventados. La base es temporal, pero `unittest discover` comparte proceso
con otros ficheros: cada test limpia al entrar y al salir.
"""
import os
import sqlite3
import tempfile
import threading
import time
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-renta-carrera-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "renta-carrera.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.config import DB_PATH  # noqa: E402
from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import renta  # noqa: E402
from app.services.categorizer import resolve_category  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class _Limpio(unittest.TestCase):
    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))

    def tearDown(self):
        with cursor() as cur:
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    @staticmethod
    def _cuantas(nombre):
        with cursor() as cur:
            return cur.execute("SELECT COUNT(*) FROM categories WHERE parent_id IS NULL AND name = ?",
                               (nombre,)).fetchone()[0]


class TestDosALaVez(_Limpio):
    def test_dos_primeras_aperturas_a_la_vez_no_fallan_ni_duplican(self):
        # Frena la creación para que las dos peticiones se pisen seguro: sin
        # el arreglo, la segunda veía que faltaban y fallaba al crearlas.
        original = renta.resolve_category

        def lenta(*args, **kwargs):
            time.sleep(0.1)
            return original(*args, **kwargs)

        respuestas = []
        renta.resolve_category = lenta
        try:
            hilos = [threading.Thread(target=lambda: respuestas.append(client.get("/renta").status_code))
                     for _ in range(2)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(30)
        finally:
            renta.resolve_category = original
        self.assertEqual(sorted(respuestas), [200, 200])
        self.assertEqual(self._cuantas("Inmueble alquilado"), 1)


class TestUnaSolaPrincipal(_Limpio):
    def test_la_base_no_admite_dos_principales_con_el_mismo_nombre(self):
        with cursor() as cur:
            cur.execute("INSERT INTO categories(name, kind) VALUES ('Principal de prueba', 'expense')")
        with self.assertRaises(sqlite3.IntegrityError):
            with cursor() as cur:
                cur.execute("INSERT INTO categories(name, kind) VALUES ('principal DE prueba', 'expense')")
        self.assertEqual(self._cuantas("Principal de prueba"), 1)

    def test_resolve_category_reutiliza_la_que_ya_esta(self):
        with cursor() as cur:
            primera = resolve_category(cur, "Principal de prueba")
            self.assertEqual(resolve_category(cur, "PRINCIPAL de prueba"), primera)

    def test_en_una_base_con_repetidas_el_indice_no_impide_arrancar(self):
        # Si alguna base vieja ya las tuviera repetidas, crear el índice
        # fallaría y la app no arrancaría: entonces no se crea.
        ruta = os.path.join(_TMP, "con-repetidas.db")
        con = sqlite3.connect(ruta, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE categories(id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER, "
                    "kind TEXT NOT NULL DEFAULT 'expense', icon TEXT, color TEXT, UNIQUE(name, parent_id))")
        con.execute("INSERT INTO categories(name) VALUES ('Repetida'), ('Repetida')")
        db._indice_principales(con.cursor())
        self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name = 'idx_categorias_principales'").fetchone())
        con.close()


class TestCursorInmediato(unittest.TestCase):
    def test_pide_la_escritura_desde_el_principio(self):
        with cursor(inmediata=True):
            otra = sqlite3.connect(DB_PATH, isolation_level=None, timeout=0)
            with self.assertRaises(sqlite3.OperationalError):
                otra.execute("BEGIN IMMEDIATE")
            otra.close()


if __name__ == "__main__":
    unittest.main()
