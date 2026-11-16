"""
Tests de lo que viaja al instalar y al empaquetar.

Lo que git ignora no es código: la base, los extractos, las capturas con datos
de verdad. Tres veces se ha colado algo de eso —el instalador se llevaba las
subcarpetas de data/, el paquete para otro PC también, y sin rsync el
instalador copiaba los extractos de la raíz— y las tres por lo mismo: cada
script llevaba su lista de exclusiones, a mano, y se desfasaba de .gitignore.

Ahora la lista es una (packaging/ficheros.sh) y aquí se comprueba con ficheros
de verdad: se monta un proyecto de mentira con un señuelo por cada patrón de
.gitignore, se instala y se empaqueta por todos los caminos, y ningún señuelo
puede aparecer al otro lado. Un patrón nuevo en .gitignore sin su señuelo hace
fallar el primer test, que dice qué hay que añadir.

Todo ocurre en carpetas temporales, con los scripts de packaging/ de verdad:
no toca la instalación ni lee un solo dato real.
"""
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MARCA = b"SENUELO: esto no puede viajar\n"
# Sin los ajustes de git de la máquina: ni su lista global de ignorados ni sus ganchos.
ENTORNO = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

# Un señuelo, o varios, por cada patrón de .gitignore. El primero de cada lista
# es uno que solo ese patrón ignora.
SENUELOS = {
    "/data/": ["data/importacion-homebank-2025/config.json", "data/tnt.db"],
    "*.db": ["copia.db", "app/copia.db"],
    "*.db-journal": ["copia.db-journal"],
    "*.db-wal": ["copia.db-wal"],
    "*.db-shm": ["copia.db-shm"],
    "*.xls": ["movements-01012026.xls"],
    "*.xlsx": ["libro.xlsx"],
    "*.csv": ["download.csv", "Carga_Homebank_ENE2026.csv"],
    "*.ofx": ["cuenta.ofx"],
    "*.pdf": ["extracto.pdf", "docs/otro.pdf"],
    "/extracts/": ["extracts/enero.txt"],
    ".venv/": [".venv/bin/activate"],
    "__pycache__/": ["app/__pycache__/nota.txt"],
    "*.pyc": ["app/suelto.pyc"],
    "*.pyo": ["app/suelto.pyo"],
    ".pytest_cache/": [".pytest_cache/README.md"],
    ".vscode/": [".vscode/settings.json"],
    ".idea/": [".idea/workspace.xml"],
    "*.swp": ["app/.main.py.swp"],
    ".DS_Store": [".DS_Store", "app/.DS_Store"],
    "*.log": ["tnt.log"],
    "/logs/": ["logs/tnt-20260101.txt"],
    "/packaging/dist/": ["packaging/dist/tnt-viejo.tar.gz"],
    "/reinstalarcambios.txt": ["reinstalarcambios.txt"],
    ".claude/settings.local.json": [".claude/settings.local.json"],
    ".env.local": [".env.local"],
    "explorations/**/our-build-*.png": ["explorations/panel/our-build-1.png"],
    "explorations/**/diff-*.png": ["explorations/panel/diff-1.png"],
    "/mockups/": ["mockups/panel.html"],
}
VIAJAN = {"app/main.py", "app/static/css/base.css", "docs/Manual-TNT.md", "docs/Manual-TNT.pdf",
          "requirements.txt", "explorations/panel/boceto.png", ".gitignore",
          "packaging/install.sh", "packaging/ficheros.sh"}
DEL_AGENTE = ".claude/launch.json"     # git lo sigue, pero no es de la app
NUEVO = "app/nuevo_sin_seguir.py"      # recién creado: git ni lo sigue ni lo ignora
BORRADO = "app/borrado.py"             # git lo sigue todavía, pero ya no está en el disco
# Lo que ya había en la instalación antes de reinstalar.
DEL_USUARIO = {"data/tnt.db": b"la base del usuario", "logs/tnt-ayer.log": b"registro",
               ".venv/pyvenv.cfg": b"entorno"}
VIEJO = "app/viejo.py"                 # estaba instalado y ya no está en el origen


def _escribir(raiz: Path, ruta: str, contenido: bytes = b"codigo\n") -> None:
    destino = raiz / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)


def _ficheros(raiz: Path) -> dict[str, bytes]:
    return {p.relative_to(raiz).as_posix(): p.read_bytes()
            for p in raiz.rglob("*") if p.is_file() and not p.is_symlink()}


def _del_paquete(tarball: Path) -> dict[str, bytes]:
    with tarfile.open(tarball) as tar:
        return {m.name.split("/", 1)[1]: tar.extractfile(m).read() for m in tar if m.isfile()}


def _lanzar(orden: list, **kwargs) -> None:
    r = subprocess.run([str(o) for o in orden], capture_output=True, text=True, timeout=120, **kwargs)
    if r.returncode != 0:
        raise AssertionError(f"{orden[0]} ha fallado ({r.returncode}):\n{r.stdout}\n{r.stderr}")


def _proyecto(tmp: Path, con_git: bool) -> Path:
    """Un proyecto de mentira con los scripts de packaging/ de verdad. Su nombre
    lleva un espacio: las rutas tienen que ir entre comillas."""
    raiz = tmp / "proyecto de prueba"
    shutil.copytree(RAIZ / "packaging", raiz / "packaging", ignore=shutil.ignore_patterns("dist"))
    shutil.copy(RAIZ / ".gitignore", raiz / ".gitignore")
    for ruta in VIAJAN - {".gitignore", "packaging/install.sh", "packaging/ficheros.sh"}:
        _escribir(raiz, ruta)
    _escribir(raiz, DEL_AGENTE)
    for rutas in SENUELOS.values():
        for ruta in rutas:
            _escribir(raiz, ruta, MARCA)
    if con_git:
        _escribir(raiz, BORRADO)
        _lanzar(["git", "init", "-q"], cwd=raiz, env=ENTORNO)
        _lanzar(["git", "add", "-A"], cwd=raiz, env=ENTORNO)   # sin commit: no hacen falta ganchos
        (raiz / BORRADO).unlink()
    _escribir(raiz, NUEVO)
    return raiz


def _instalar(raiz: Path, prefijo: Path, entorno: dict) -> dict[str, bytes]:
    """Reinstala sobre una instalación que ya tiene datos y un fichero viejo."""
    app = prefijo / "share" / "tnt"
    for ruta, contenido in DEL_USUARIO.items():
        _escribir(app, ruta, contenido)
    _escribir(app, VIEJO)
    _lanzar([raiz / "packaging" / "install.sh", "--no-venv", f"--prefix={prefijo}"], env=entorno)
    return _ficheros(app)


def _sin_rsync(tmp: Path) -> dict:
    """Un PATH con lo justo para el instalador, y sin rsync."""
    carpeta = tmp / "bin"
    carpeta.mkdir()
    for orden in ("bash", "python3", "readlink", "dirname", "cat", "mkdir", "tar", "cp", "chmod", "sed"):
        os.symlink(shutil.which(orden), carpeta / orden)
    assert shutil.which("rsync", path=str(carpeta)) is None
    return {**ENTORNO, "PATH": str(carpeta)}


@unittest.skipUnless(shutil.which("git") and shutil.which("tar"), "hacen falta git y tar")
class TestLoQueViaja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="tnt-empaquetado-test-")
        tmp = Path(cls._tmp.name)
        cls.raiz = raiz = _proyecto(tmp, con_git=True)
        cls.ignorados = subprocess.run(
            ["git", "check-ignore", "-v", "-n", "--stdin"], cwd=raiz, env=ENTORNO, capture_output=True,
            text=True, input="\n".join(r for rutas in SENUELOS.values() for r in rutas)).stdout
        cls.con_rsync = (_instalar(raiz, tmp / "instalado con rsync", ENTORNO)
                         if shutil.which("rsync") else None)
        cls.con_tar = _instalar(raiz, tmp / "instalado con tar", _sin_rsync(tmp))
        _lanzar([raiz / "packaging" / "package.sh", "con-git"], env=ENTORNO)
        cls.paquete = _del_paquete(raiz / "packaging" / "dist" / "tnt-con-git.tar.gz")
        # El mismo proyecto fuera de git, y dentro de un repositorio que no es el suyo.
        ajeno = tmp / "repositorio ajeno"
        ajeno.mkdir()
        _lanzar(["git", "init", "-q"], cwd=ajeno, env=ENTORNO)
        suelto = _proyecto(ajeno, con_git=False)
        _lanzar([suelto / "packaging" / "package.sh", "sin-git"], env=ENTORNO)
        cls.paquete_sin_git = _del_paquete(suelto / "packaging" / "dist" / "tnt-sin-git.tar.gz")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _caminos(self):
        caminos = {"instalar con tar": self.con_tar, "paquete": self.paquete,
                   "paquete sin git": self.paquete_sin_git}
        if self.con_rsync is not None:
            caminos["instalar con rsync"] = self.con_rsync
        return caminos

    # ── la regla: .gitignore y los señuelos van a la par ──────────────────

    def test_cada_patron_de_gitignore_tiene_su_senuelo(self):
        lineas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
        patrones = {l.strip() for l in lineas if l.strip() and not l.strip().startswith(("#", "!"))}
        self.assertEqual(
            patrones, set(SENUELOS),
            "Los patrones de .gitignore y SENUELOS (en este fichero) no coinciden. A un patrón nuevo "
            "ponle aquí un fichero de ejemplo: así se comprueba que no viaja ni al instalar ni al "
            "empaquetar. Si entonces falla otro test, exclúyelo también en packaging/ficheros.sh.")

    def test_a_cada_senuelo_lo_ignora_git_y_a_uno_por_su_patron(self):
        quien = {}
        for linea in self.ignorados.splitlines():
            origen, ruta = linea.split("\t")
            quien[ruta] = origen.split(":", 2)[2]
        for patron, rutas in SENUELOS.items():
            with self.subTest(patron=patron):
                self.assertTrue(all(quien.get(r) for r in rutas), f"git no ignora alguno de {rutas}")
                self.assertEqual(quien[rutas[0]], patron)

    # ── lo que no puede viajar, por ningún camino ─────────────────────────

    def test_ningun_senuelo_viaja(self):
        for camino, ficheros in self._caminos().items():
            with self.subTest(camino=camino):
                self.assertEqual(sorted(r for r, c in ficheros.items() if c == MARCA), [])

    def test_los_ajustes_del_agente_y_git_no_viajan(self):
        for camino, ficheros in self._caminos().items():
            with self.subTest(camino=camino):
                self.assertEqual([r for r in ficheros if r.startswith((".claude/", ".git/"))], [])

    # ── lo que sí ────────────────────────────────────────────────────────

    def test_el_codigo_y_el_manual_en_pdf_viajan(self):
        for camino, ficheros in self._caminos().items():
            with self.subTest(camino=camino):
                self.assertEqual(VIAJAN - set(ficheros), set())

    def test_al_instalar_viaja_lo_nuevo_aunque_git_aun_no_lo_siga(self):
        # Si no, lo recién escrito faltaría en la instalación hasta el commit.
        for camino in ("instalar con rsync", "instalar con tar"):
            if camino in self._caminos():
                with self.subTest(camino=camino):
                    self.assertIn(NUEVO, self._caminos()[camino])

    def test_el_paquete_lleva_solo_lo_que_sigue_git(self):
        # Lo que sale de este PC es más estricto: sin añadir a git, no viaja.
        self.assertNotIn(NUEVO, self.paquete)

    def test_un_fichero_seguido_que_ya_no_esta_no_impide_empaquetar(self):
        # Borrado del disco sin commit: el paquete sale, y sale sin él.
        self.assertNotIn(BORRADO, self.paquete)
        self.assertIn("app/main.py", self.paquete)

    def test_un_paquete_dentro_de_un_repositorio_ajeno_no_sale_vacio(self):
        self.assertIn(NUEVO, self.paquete_sin_git)

    # ── reinstalar ───────────────────────────────────────────────────────

    def test_reinstalar_no_toca_los_datos_del_usuario(self):
        for camino in ("instalar con rsync", "instalar con tar"):
            if camino in self._caminos():
                with self.subTest(camino=camino):
                    ficheros = self._caminos()[camino]
                    self.assertEqual({r: ficheros.get(r) for r in DEL_USUARIO}, DEL_USUARIO)

    @unittest.skipUnless(shutil.which("rsync"), "hace falta rsync")
    def test_con_rsync_lo_que_ya_no_esta_en_el_origen_se_va(self):
        self.assertNotIn(VIEJO, self.con_rsync)

    def test_sin_rsync_copia_tar_que_no_borra_lo_viejo(self):
        # Es también la prueba de que este camino no ha usado rsync.
        self.assertIn(VIEJO, self.con_tar)


if __name__ == "__main__":
    unittest.main()
