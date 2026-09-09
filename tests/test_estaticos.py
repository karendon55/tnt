"""
Tests de la hoja de estilos: que exista entera y que no vuelva a engordar.

Dos cosas que fallan en silencio:

1. Un `<link>` a un CSS que no existe. El navegador no avisa en ninguna parte
   visible: la página sale sin estilos y a ver quién adivina por qué. Desde que
   la hoja son cinco ficheros, la probabilidad de una errata se multiplica.

2. El tope de líneas del estándar. `tnt.css` llegó a 535 con el tope duro en
   500, y nadie se enteró hasta auditarlo a mano. Aquí se entera solo.
"""
import os
import re
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="tnt-css-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "css.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import STATIC_DIR, TEMPLATES_DIR  # noqa: E402
from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

TOPE_DURO = 500      # del estándar: ~/.claude/standards/ENGINEERING-AND-DESIGN.md
TOPE_BLANDO = 350

# El orden de carga ES la cascada. Si alguien reordena los <link>, cambia el
# resultado visual sin tocar una sola regla, así que el orden se fija aquí.
ORDEN = ["tokens.css", "base.css", "componentes.css", "patrones.css", "pantallas.css"]


def hojas_enlazadas(html: str) -> list[str]:
    """Los CSS propios que la página enlaza, en orden. El de Basecoat va por CDN."""
    return re.findall(r'href="/static/css/([^"?]+)', html)


class TestHojasDeEstilo(unittest.TestCase):
    def test_las_que_enlaza_la_pagina_existen_y_se_sirven(self):
        html = client.get("/").text
        hojas = hojas_enlazadas(html)
        self.assertTrue(hojas, "la página no enlaza ninguna hoja de estilos")
        for hoja in hojas:
            with self.subTest(hoja=hoja):
                self.assertTrue((STATIC_DIR / "css" / hoja).is_file(),
                                f"{hoja} está enlazada pero no existe en disco")
                r = client.get(f"/static/css/{hoja}")
                self.assertEqual(r.status_code, 200)

    def test_el_orden_de_carga_es_el_de_la_cascada(self):
        self.assertEqual(hojas_enlazadas(client.get("/").text), ORDEN)

    def test_todas_las_hojas_del_directorio_estan_enlazadas(self):
        """Un CSS que nadie enlaza es código muerto que parece vivo."""
        en_disco = sorted(p.name for p in (STATIC_DIR / "css").glob("*.css"))
        self.assertEqual(en_disco, sorted(ORDEN))

    def test_ninguna_pasa_del_tope_duro(self):
        for p in sorted((STATIC_DIR / "css").glob("*.css")):
            with self.subTest(hoja=p.name):
                n = len(p.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(
                    n, TOPE_DURO,
                    f"{p.name} tiene {n} líneas; el tope duro son {TOPE_DURO}. "
                    f"Pártela por secciones, sin reordenar reglas.")

    def test_el_sello_de_cache_cambia_en_la_pagina_cuando_cambia_una_hoja(self):
        """Sin esto el navegador sirve la hoja vieja durante horas.

        Se mira el HTML servido, no la función que calcula el sello: el sello
        se guardaba al importar el módulo y la función, llamada a mano, daba el
        valor nuevo mientras la página seguía enseñando el viejo. Un test que
        pasaba y un navegador que no se enteraba."""
        antes = set(re.findall(r"/static/css/[^\"]+", client.get("/").text))
        objetivo = STATIC_DIR / "css" / "pantallas.css"
        mtime = objetivo.stat().st_mtime
        # bien por delante: el sello es el MÁXIMO de todas las fechas, así que
        # sumar unos segundos a un fichero que no es el más nuevo no cambia nada
        futuro = mtime + 100_000
        try:
            os.utime(objetivo, (futuro, futuro))
            despues = set(re.findall(r"/static/css/[^\"]+", client.get("/").text))
        finally:
            os.utime(objetivo, (mtime, mtime))
        self.assertNotEqual(antes, despues,
                            "la página siguió pidiendo el CSS con el sello viejo")


class TestClasesQueExisten(unittest.TestCase):
    """Una clase escrita en una plantilla y no definida en ninguna parte no da
    error: el elemento sale sin estilo y a ver quién lo ve.

    Pasó de verdad. `dashboard_empty.html` usaba `.empty-bolt` para dar tamaño
    a un rayo SVG; la clase no existía en el CSS, así que el SVG se estiró a
    1185 × 1580 px y se comió la primera pantalla que ve alguien que acaba de
    instalar TNT. Meses así, porque solo aparece con la base vacía.

    Una clase vale si la pinta el CSS o si la busca algún JavaScript (hay
    clases que solo son un gancho: `.enc-only`, `.fund-chart`). Lo que no vale
    es que no la conozca nadie."""

    JINJA = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.S)

    @classmethod
    def setUpClass(cls):
        css = "\n".join(p.read_text(encoding="utf-8")
                        for p in (STATIC_DIR / "css").glob("*.css"))
        cls.pintadas = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
        cls.js = "\n".join(p.read_text(encoding="utf-8")
                           for p in (STATIC_DIR / "js").glob("*.js"))

    def test_ninguna_clase_de_plantilla_se_queda_sin_dueno(self):
        plantillas = sorted((TEMPLATES_DIR).glob("*.html"))
        self.assertTrue(plantillas, "no se encontró ninguna plantilla")
        for t in plantillas:
            texto = t.read_text(encoding="utf-8")
            usadas = set()
            for attr in re.findall(r'class="([^"]*)"', texto):
                usadas.update(self.JINJA.sub(" ", attr).split())
            for clase in sorted(usadas - self.pintadas):
                with self.subTest(plantilla=t.name, clase=clase):
                    # un gancho se escribe con el punto: querySelectorAll('.x')
                    gancho = f".{clase}" in texto or f".{clase}" in self.js
                    self.assertTrue(
                        gancho,
                        f"{t.name} usa .{clase}, que no está en el CSS ni la "
                        f"busca ningún JavaScript")


class TestAvisoDeTamano(unittest.TestCase):
    def test_ninguna_pasa_del_tope_blando_sin_que_conste(self):
        """No falla: informa. El tope blando es una conversación, no una regla."""
        gordas = [(p.name, len(p.read_text(encoding="utf-8").splitlines()))
                  for p in sorted((STATIC_DIR / "css").glob("*.css"))]
        pasadas = [(n, c) for n, c in gordas if c > TOPE_BLANDO]
        if pasadas:
            print(f"\n  aviso: por encima del tope blando ({TOPE_BLANDO}): {pasadas}")


if __name__ == "__main__":
    unittest.main()
