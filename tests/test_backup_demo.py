"""
El modo demostración no puede escribir encima de los backups de verdad.

Los destinos de backup (~/Dropbox, la carpeta de contabilidad) son los mismos
en cualquier sesión, así que pulsar «Hacer backup» con la base de mentira
cargada dejaría los datos inventados donde deberían estar las copias buenas.
La pantalla se puede seguir mirando; lo que se bloquea es la escritura.

El modo demostración se enciende aquí, en el router, y no con TNT_DEMO al
cargar: eso solo valía si este fichero era el primero en cargar la app. El
17/11/2026, lanzado detrás de otro, el bloqueo no estaba puesto y el backup se
hizo de verdad encima de los del usuario. Por si el bloqueo fallara, la
carpeta personal es una temporal, y se comprueba que en ella no se escribe
nada. El último test demuestra que esa comprobación sí ve una escritura.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="tnt-demo-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "demo.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import backup as rutas  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class TestBackupBloqueadoEnDemo(unittest.TestCase):
    def setUp(self):
        self.casa = Path(tempfile.mkdtemp(prefix="casa-", dir=_TMP))
        base = Path(tempfile.mkdtemp(prefix="base-", dir=_TMP)) / "tnt.db"
        sqlite3.connect(base).close()
        for parche in (mock.patch.dict(os.environ, {"HOME": str(self.casa)}),
                       mock.patch.object(rutas, "DEMO_MODE", True),
                       mock.patch.object(rutas, "DB_PATH", base)):
            parche.start()
            self.addCleanup(parche.stop)
        # Sin destinos guardados, valen los de fábrica: ~/Dropbox y la carpeta
        # de contabilidad, que aquí caen dentro de la carpeta temporal.
        with cursor() as cur:
            cur.execute("DELETE FROM settings WHERE key = 'backup_destinations'")
        self.assertEqual(Path("~/Dropbox").expanduser(), self.casa / "Dropbox")

    def _escrito(self) -> list[str]:
        return sorted(str(p.relative_to(self.casa)) for p in self.casa.rglob("*") if p.is_file())

    def test_backup_a_todos_los_destinos_no_escribe(self):
        r = client.post("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("modo demostración", r.text)
        self.assertEqual(self._escrito(), [])

    def test_backup_a_un_destino_no_escribe(self):
        r = client.post("/backup/destino", data={"dest_index": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("modo demostración", r.text)
        self.assertEqual(self._escrito(), [])

    def test_la_pantalla_sigue_viéndose(self):
        """Bloquear la escritura no es esconder la sección."""
        r = client.get("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Backup y restauración", r.text)

    def test_sin_el_modo_demostracion_si_escribe_y_se_ve(self):
        """Control: si el bloqueo no estuviera, la comprobación lo vería."""
        with mock.patch.object(rutas, "DEMO_MODE", False):
            client.post("/backup")
        self.assertEqual(self._escrito(), ["Documentos/contabilidad/backup/tnt.db", "Dropbox/tnt.db"])


if __name__ == "__main__":
    unittest.main()
