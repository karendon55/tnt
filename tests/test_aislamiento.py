"""
Los tests corren aislados de la carpeta personal y de la base de verdad.

Si esto falla, no lances más tests de esa manera: pueden escribir encima de tus
backups (ver tests/__init__.py). Lánzalos con ./run_tests.sh o con
`python -m unittest tests.<fichero>`.
"""
import os
import pwd
import tempfile
import unittest
from pathlib import Path

import tests
from app.config import BASE_DIR, DB_PATH
from app.services import master_key

CASA_REAL = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
CASA = Path(tests.CASA_DE_PRUEBA)
COMO = "Lanza los tests con ./run_tests.sh o con python -m unittest tests.<fichero>."


class TestAislamiento(unittest.TestCase):
    def test_la_carpeta_personal_es_la_de_prueba(self):
        self.assertEqual(Path.home(), CASA, COMO)
        self.assertNotEqual(CASA.resolve(), CASA_REAL)

    def test_los_backups_por_defecto_caen_en_la_de_prueba(self):
        for destino in ("~/Dropbox", "~/Documentos/contabilidad/backup"):
            with self.subTest(destino=destino):
                self.assertEqual(Path(destino).expanduser(), CASA / destino[2:], COMO)

    def test_la_clave_maestra_no_es_la_de_verdad(self):
        self.assertEqual(master_key.key_path(), CASA / ".config" / "tnt" / "master.key", COMO)

    def test_la_base_es_temporal(self):
        base = DB_PATH.resolve()
        self.assertTrue(base.is_relative_to(Path(tempfile.gettempdir()).resolve()), base)
        self.assertNotIn(base, {CASA_REAL / ".local" / "share" / "tnt" / "data" / "tnt.db",
                                (BASE_DIR / "data" / "tnt.db").resolve()})


if __name__ == "__main__":
    unittest.main()
