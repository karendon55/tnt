"""
El modo demostración no puede escribir encima de los backups de verdad.

Los destinos de backup (~/Dropbox, la carpeta de contabilidad) son los mismos
en cualquier sesión, así que pulsar «Hacer backup» con la base de mentira
cargada dejaría los datos inventados donde deberían estar las copias buenas.
La pantalla se puede seguir mirando; lo que se bloquea es la escritura.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-demo-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "demo.db")
os.environ["TNT_DEMO"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import DEMO_MODE  # noqa: E402
from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class TestBackupBloqueadoEnDemo(unittest.TestCase):
    def test_el_modo_demo_esta_activo_en_este_fichero(self):
        """Si esto falla, los demás tests de aquí no prueban nada."""
        self.assertTrue(DEMO_MODE)

    def test_backup_a_todos_los_destinos_no_escribe(self):
        r = client.post("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("modo demostración", r.text)

    def test_backup_a_un_destino_no_escribe(self):
        r = client.post("/backup/destino", data={"dest_index": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("modo demostración", r.text)

    def test_la_pantalla_sigue_viéndose(self):
        """Bloquear la escritura no es esconder la sección."""
        r = client.get("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Backup y restauración", r.text)


if __name__ == "__main__":
    unittest.main()
