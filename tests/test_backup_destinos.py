"""
Tests de los destinos de backup, las copias y el backup cifrado, por sus rutas.

Qué tiene que cumplir un backup: la copia es la base entera (también lo último
que se escribió), un destino que falla no impide los demás, la contraseña de un
destino cifrado nunca se guarda ni se enseña en claro, y restaurar deja a mano
la base que había.

OJO con dónde escriben: un backup de verdad va a ~/Dropbox y a la carpeta de
contabilidad. Aquí, mientras dura cada test, la carpeta personal es una
temporal (si no lo fuera, el test falla antes de pedir nada), la clave maestra
es otra de usar y tirar, y la base que se copia y se restaura es una de
juguete, no la que comparten los demás tests.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

_TMP = tempfile.mkdtemp(prefix="tnt-backup-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "backup.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import backup as rutas  # noqa: E402
from app.services import encrypted_backup, master_key  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")
CLAVE = "backup_destinations"
SECRETO = "secreto-largo"
_derivar = encrypted_backup._derive_key


def _marca(base: Path) -> list[str]:
    con = sqlite3.connect(base)
    try:
        return [r[0] for r in con.execute("SELECT texto FROM marca ORDER BY rowid")]
    finally:
        con.close()


class _Aislado(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="caso-", dir=_TMP))
        casa = self.tmp / "casa"
        casa.mkdir()
        self.base = self.tmp / "tnt.db"
        con = sqlite3.connect(self.base)
        con.execute("CREATE TABLE marca(texto TEXT)")
        con.execute("INSERT INTO marca VALUES ('original')")
        con.commit()
        con.close()
        for parche in (
                mock.patch.dict(os.environ, {"HOME": str(casa)}),
                mock.patch.object(master_key, "_KEY_PATH", self.tmp / "master.key"),
                mock.patch.object(rutas, "DB_PATH", self.base),
                mock.patch.object(rutas, "DEMO_MODE", False),
                # La derivación de verdad tarda medio segundo: aquí, la mínima.
                mock.patch.object(encrypted_backup, "_derive_key", lambda p, sal, _: _derivar(p, sal, 10_000))):
            parche.start()
            self.addCleanup(parche.stop)
        # Si la carpeta personal no es la temporal, un backup escribiría en la de verdad.
        self.assertEqual(Path("~/Dropbox").expanduser(), casa / "Dropbox")
        self.a, self.b = self.tmp / "destino a", self.tmp / "destino b"
        self._escribir_ajuste(None)
        self.addCleanup(self._escribir_ajuste, None)

    @staticmethod
    def _escribir_ajuste(valor: str | None) -> None:
        with cursor() as cur:
            cur.execute("DELETE FROM settings WHERE key = ?", (CLAVE,))
            if valor is not None:
                cur.execute("INSERT INTO settings(key, value) VALUES (?, ?)", (CLAVE, valor))

    @staticmethod
    def _guardado() -> list:
        with cursor() as cur:
            return json.loads(cur.execute("SELECT value FROM settings WHERE key = ?", (CLAVE,)).fetchone()[0])

    def _destinos(self, texto: str) -> None:
        r = client.post("/backup/destinos", data={"destinations_text": texto}, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/backup"))

    @staticmethod
    def _configurar(indice: int, modo: str, password: str = "", confirm: str | None = None) -> str:
        r = client.post("/backup/destino/config", follow_redirects=False, data={
            "dest_index": str(indice), "mode": modo, "password": password,
            "confirm": password if confirm is None else confirm})
        assert r.status_code == 303, r.status_code
        return unquote(r.headers["location"])

    def _descifrada(self, fichero: Path) -> list[str]:
        claro = self.tmp / "descifrada.db"
        claro.write_bytes(encrypted_backup.unpack(fichero.read_bytes(), SECRETO))
        return _marca(claro)


class TestDestinos(_Aislado):
    def test_la_lista_se_guarda_una_ruta_por_linea(self):
        self._destinos(f"  {self.a}  \n\n{self.b}\n   \n")
        self.assertEqual(self._guardado(), [{"path": str(self.a), "mode": "plain"},
                                            {"path": str(self.b), "mode": "plain"}])

    def test_sin_configurar_propone_los_de_fabrica(self):
        r = client.get("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([d["path"] for d in self._guardado()], ["~/Dropbox", "~/Documentos/contabilidad/backup"])
        self.assertIn("~/Dropbox", r.text)

    def test_una_configuracion_ilegible_vuelve_a_los_de_fabrica(self):
        self._escribir_ajuste("{esto no es json")
        r = client.get("/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("~/Documentos/contabilidad/backup", r.text)

    def test_cifrar_un_destino_guarda_la_contraseña_cifrada_y_no_la_enseña(self):
        self._destinos(str(self.a))
        self.assertEqual(self._configurar(0, "encrypted", SECRETO), "/backup?saved=1")
        (destino,) = self._guardado()
        self.assertEqual(destino["mode"], "encrypted")
        self.assertTrue(destino["password"].startswith("enc:"))
        self.assertNotIn(SECRETO, json.dumps(self._guardado()))
        self.assertEqual(master_key.decrypt_secret(destino["password"]), SECRETO)
        pagina = client.get("/backup").text
        self.assertIn("contraseña guardada", pagina)
        self.assertNotIn(SECRETO, pagina)
        self.assertNotIn(destino["password"], pagina)

    def test_una_contraseña_corta_o_que_no_coincide_no_se_guarda(self):
        self._destinos(str(self.a))
        self.assertIn("al menos 8 caracteres", self._configurar(0, "encrypted", "corta"))
        self.assertIn("no coinciden", self._configurar(0, "encrypted", SECRETO, confirm="otra-distinta"))
        self.assertEqual(self._guardado(), [{"path": str(self.a), "mode": "plain"}])

    def test_cifrado_sin_escribir_contraseña_mantiene_la_que_habia(self):
        self._destinos(str(self.a))
        self._configurar(0, "encrypted", SECRETO)
        antes = self._guardado()
        self.assertEqual(self._configurar(0, "encrypted"), "/backup?saved=1")
        self.assertEqual(self._guardado(), antes)

    def test_volver_a_sin_cifrar_olvida_la_contraseña(self):
        self._destinos(str(self.a))
        self._configurar(0, "encrypted", SECRETO)
        self._configurar(0, "plain")
        self.assertEqual(self._guardado(), [{"path": str(self.a), "mode": "plain"}])

    def test_cambiar_la_lista_conserva_el_modo_y_la_contraseña_de_los_que_siguen(self):
        self._destinos(str(self.a))
        self._configurar(0, "encrypted", SECRETO)
        (cifrado,) = self._guardado()
        self._destinos(f"{self.b}\n{self.a}")
        self.assertEqual(self._guardado(), [{"path": str(self.b), "mode": "plain"}, cifrado])

    def test_un_destino_o_un_modo_que_no_existen_no_cambian_nada(self):
        self._destinos(str(self.a))
        self.assertEqual(self._configurar(5, "encrypted", SECRETO), "/backup")
        self.assertEqual(self._configurar(0, "raro", SECRETO), "/backup")
        self.assertEqual(self._guardado(), [{"path": str(self.a), "mode": "plain"}])

    def test_el_formato_antiguo_se_lee_y_su_contraseña_en_claro_se_cifra(self):
        self._escribir_ajuste(json.dumps(
            [str(self.a), {"path": str(self.b), "mode": "encrypted", "password": "en-claro-123"}]))
        self.assertEqual(client.get("/backup").status_code, 200)
        llano, cifrado = self._guardado()
        self.assertEqual(llano, {"path": str(self.a), "mode": "plain"})
        self.assertTrue(cifrado["password"].startswith("enc:"))
        self.assertEqual(master_key.decrypt_secret(cifrado["password"]), "en-claro-123")


class TestCopias(_Aislado):
    def setUp(self):
        super().setUp()
        self._destinos(f"{self.a}\n{self.b}")
        self._configurar(1, "encrypted", SECRETO)

    def test_backup_a_todos_copia_la_base_a_cada_destino_en_su_modo(self):
        r = client.post("/backup")
        self.assertIn("Backup ok", r.text)
        self.assertEqual(_marca(self.a / "tnt.db"), ["original"])
        self.assertEqual(self._descifrada(self.b / "tnt.db.tnt"), ["original"])
        self.assertEqual(sorted(p.name for d in (self.a, self.b) for p in d.iterdir()), ["tnt.db", "tnt.db.tnt"])

    def test_la_copia_lleva_lo_ultimo_aunque_aun_este_en_el_wal(self):
        # Con la app abierta, lo recién escrito vive en el -wal: copiar tnt.db
        # a secas lo perdería.
        con = sqlite3.connect(self.base)
        self.addCleanup(con.close)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("INSERT INTO marca VALUES ('reciente')")
        con.commit()
        client.post("/backup")
        self.assertEqual(_marca(self.a / "tnt.db"), ["original", "reciente"])
        self.assertEqual(self._descifrada(self.b / "tnt.db.tnt"), ["original", "reciente"])

    def test_cambiar_de_modo_quita_la_copia_del_modo_anterior(self):
        client.post("/backup")
        self._configurar(0, "encrypted", SECRETO)
        self._configurar(1, "plain")
        client.post("/backup")
        self.assertEqual([p.name for p in self.a.iterdir()], ["tnt.db.tnt"])
        self.assertEqual([p.name for p in self.b.iterdir()], ["tnt.db"])

    def test_un_destino_que_falla_no_impide_los_demas(self):
        (self.tmp / "estorbo").write_text("un fichero donde debería ir una carpeta")
        self._destinos(f"{self.tmp / 'estorbo' / 'dentro'}\n{self.a}")
        r = client.post("/backup")
        self.assertIn("Backup parcial", r.text)
        self.assertIn("falló", r.text)
        self.assertEqual(_marca(self.a / "tnt.db"), ["original"])

    def test_cifrado_sin_contraseña_avisa_y_no_copia_en_claro(self):
        self._escribir_ajuste(json.dumps([{"path": str(self.a), "mode": "encrypted"}]))
        r = client.post("/backup")
        self.assertIn("Modo cifrado sin contraseña configurada", r.text)
        self.assertFalse(self.a.exists())

    def test_backup_a_un_solo_destino_no_toca_los_demas(self):
        r = client.post("/backup/destino", data={"dest_index": "1"})
        self.assertIn("Cifrado", r.text)
        self.assertEqual(self._descifrada(self.b / "tnt.db.tnt"), ["original"])
        self.assertFalse(self.a.exists())

    def test_un_destino_que_no_existe_o_una_base_que_no_esta_se_avisan(self):
        self.assertIn("Destino inválido.", client.post("/backup/destino", data={"dest_index": "7"}).text)
        with mock.patch.object(rutas, "DB_PATH", self.tmp / "no-esta.db"):
            self.assertIn("No existe", client.post("/backup").text)
            self.assertIn("No existe", client.post("/backup/destino", data={"dest_index": "0"}).text)
            r = client.post("/backup/cifrado", data={"password": SECRETO, "confirm": SECRETO})
            self.assertEqual(r.status_code, 400)
        self.assertFalse(self.a.exists())


class TestCifradoYRestaurar(_Aislado):
    def _descargar(self, password=SECRETO, confirm=SECRETO):
        return client.post("/backup/cifrado", data={"password": password, "confirm": confirm})

    def _restaurar(self, contenido: bytes, password=SECRETO):
        return client.post("/backup/restaurar", data={"password": password},
                           files={"file": ("copia.tnt", contenido, "application/octet-stream")})

    def _cambiar_la_base(self):
        con = sqlite3.connect(self.base)
        con.execute("UPDATE marca SET texto = 'cambiada'")
        con.commit()
        con.close()

    def test_la_descarga_exige_una_contraseña_larga_y_repetida(self):
        self.assertEqual(self._descargar(confirm="otra-distinta").status_code, 400)
        self.assertIn("no coinciden", self._descargar(confirm="otra-distinta").text)
        self.assertIn("al menos 8 caracteres", self._descargar("corta", "corta").text)

    def test_lo_descargado_restaura_la_base_y_deja_a_mano_la_que_habia(self):
        descarga = self._descargar()
        self.assertEqual(descarga.status_code, 200)
        self.assertRegex(descarga.headers["content-disposition"], r'filename="tnt-backup-\d{8}-\d{6}\.tnt"')
        self._cambiar_la_base()
        r = self._restaurar(descarga.content)
        self.assertIn("Restauración correcta", r.text)
        self.assertEqual(_marca(self.base), ["original"])
        (anterior,) = self.tmp.glob("tnt.db.before-restore-*")
        self.assertEqual(_marca(anterior), ["cambiada"])
        self.assertIn(str(anterior), r.text)

    def test_con_otra_contraseña_o_un_fichero_vacio_la_base_no_se_toca(self):
        copia = self._descargar().content
        self._cambiar_la_base()
        self.assertIn("Contraseña incorrecta", self._restaurar(copia, "no-es-esta").text)
        self.assertIn("El fichero está vacío.", self._restaurar(b"").text)
        self.assertIn("no parece un backup TNT", self._restaurar(b"cualquier cosa").text)
        self.assertEqual(_marca(self.base), ["cambiada"])
        self.assertEqual(list(self.tmp.glob("tnt.db.before-restore-*")), [])


if __name__ == "__main__":
    unittest.main()
