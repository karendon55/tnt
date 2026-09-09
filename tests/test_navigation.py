"""
Tests de navegación: que el menú lleve a sitios que existen y marque dónde estás.

Este fichero nace con la reestructuración de menús (Panel · Movimientos ·
Traspasos · Inversiones · Presupuestos · Configuración). Un enlace roto en la
barra superior no da error en ningún log: simplemente te lleva a un 404 el día
que pinchas ahí. Estos tests lo cazan en cada ejecución.

Cada test arranca con una base de datos vacía y recién creada en un directorio
temporal, así que no dependen de que haya datos ni tocan la base real.
"""
import os
import re
import tempfile
import unittest

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

# El esquema lo crea el lifespan de la app, que TestClient solo dispara si se
# usa como gestor de contexto. Aquí lo creamos a mano, una vez.
init_db()

# base_url local a propósito: main.py rechaza cualquier Host que no sea de
# loopback (defensa contra DNS rebinding), y el "testserver" por defecto de
# TestClient se comería un 400.
client = TestClient(app, base_url="http://127.0.0.1:8000")


def barra_superior(html: str) -> str:
    """El trozo <nav class="nav">…</nav>, sin la subnavegación de dentro."""
    return html.split('class="nav"', 1)[1].split("</nav>", 1)[0]


def enlace(fragmento: str, url: str) -> str:
    """La etiqueta <a …> completa que apunta a esa URL.

    Buscar 'lo que hay antes del href' no vale: la clase puede ir antes o
    después del href, y el orden de los atributos no es contrato de nada."""
    m = re.search(r'<a\b[^>]*href="' + re.escape(url) + r'"[^>]*>', fragmento)
    return m.group(0) if m else ""


def rutas_registradas() -> set[str]:
    """Todas las rutas, incluidas las de los routers anidados.

    FastAPI envuelve cada include_router en un objeto propio, así que
    app.routes no las trae planas."""
    encontradas: set[str] = set()

    def recorre(rutas):
        for r in rutas:
            if hasattr(r, "path"):
                encontradas.add(r.path)
            # Cada include_router queda envuelto; las suyas cuelgan de
            # original_router.routes, no de .routes.
            interno = getattr(r, "original_router", None) or getattr(r, "routes", None)
            if interno is not None:
                recorre(getattr(interno, "routes", interno))

    recorre(app.routes)
    return encontradas

# Lo que debe haber en la barra superior, en este orden.
MENU = [
    ("Panel", "/", "dashboard"),
    ("Movimientos", "/movimientos", "transactions"),
    ("Traspasos", "/traspasos", "transfers"),
    ("Inversiones", "/inversiones", "investments"),
    ("Presupuestos", "/presupuestos", "budgets"),
    ("Configuración", "/configuracion", "settings"),
]

# Lo que cuelga de Configuración. Conservan su URL de siempre a propósito.
# Traspasos NO está: vive arriba, y repetirlo aquí contradecía la propia regla
# de reparto (arriba lo del mes, en Configuración lo de vez en cuando).
CONFIGURACION = [
    ("Backup", "/backup"),
    ("Cuentas", "/cuentas"),
    ("Categorías", "/categorias"),
    ("Reglas", "/reglas"),
    ("Importar", "/importar"),
]


class TestMenuPrincipal(unittest.TestCase):
    def test_todas_las_pestanas_responden(self):
        for nombre, url, _ in MENU:
            with self.subTest(pestana=nombre):
                r = client.get(url)
                self.assertEqual(r.status_code, 200, f"{nombre} ({url}) devolvió {r.status_code}")

    def test_la_barra_lista_las_seis_pestanas(self):
        html = client.get("/").text
        for nombre, url, _ in MENU:
            with self.subTest(pestana=nombre):
                self.assertIn(f'href="{url}"', html, f"falta el enlace a {nombre}")

    def test_la_barra_no_arrastra_las_pestanas_viejas(self):
        """Cuentas, Categorías, Reglas e Importar bajan a Configuración."""
        barra = barra_superior(client.get("/").text)
        for viejo in ("/cuentas", "/categorias", "/reglas", "/importar"):
            with self.subTest(url=viejo):
                self.assertFalse(f'href="{viejo}"' in barra,
                                 f"{viejo} sigue en la barra superior")

    def test_cada_pagina_marca_su_pestana(self):
        for nombre, url, _ in MENU:
            with self.subTest(pestana=nombre):
                barra = barra_superior(client.get(url).text)
                activos = barra.count("is-active")
                self.assertEqual(activos, 1, f"{nombre} marca {activos} pestañas activas")
                self.assertIn("is-active", enlace(barra, url),
                              f"{nombre} no se marca a sí misma")


class TestConfiguracion(unittest.TestCase):
    def test_el_indice_enlaza_las_seis_secciones(self):
        html = client.get("/configuracion").text
        for nombre, url in CONFIGURACION:
            with self.subTest(seccion=nombre):
                self.assertIn(f'href="{url}"', html, f"Configuración no enlaza {nombre}")

    def test_las_seis_secciones_responden(self):
        for nombre, url in CONFIGURACION:
            with self.subTest(seccion=nombre):
                self.assertEqual(client.get(url).status_code, 200)

    def test_traspasos_no_aparece_en_configuracion(self):
        """Vive arriba. Estar en los dos sitios contradice la regla de reparto."""
        html = client.get("/configuracion").text
        # Arriba sí está, y debe estar: se mira solo lo de dentro.
        subnav = html.split('class="subnav"', 1)[1].split("</nav>", 1)[0]
        self.assertFalse("/traspasos" in subnav,
                         "Traspasos sigue en la subnavegación de Configuración")
        listado = html.split('class="settings-list"', 1)[1]
        self.assertFalse('href="/traspasos"' in listado,
                         "Traspasos sigue en la portada de Configuración")

    def test_las_secciones_se_marcan_dentro_de_configuracion(self):
        """Estando en /cuentas, la pestaña de arriba iluminada es Configuración."""
        for nombre, url in CONFIGURACION:
            with self.subTest(seccion=nombre):
                barra = barra_superior(client.get(url).text)
                self.assertIn("is-active", enlace(barra, "/configuracion"),
                              f"{nombre} no marca Configuración")


class TestRutasQueSeMudan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Una cuenta de inversión, para que Inversiones tenga algo que enseñar.

        De paso comprueba que el alta de cuenta sigue en /cuentas/nueva."""
        r = client.post("/cuentas/nueva", data={
            "name": "Fondo de prueba", "bank": "Banco Demo", "iban": "",
            "initial_balance": "0", "type": "investment",
        }, follow_redirects=False)
        assert r.status_code in (200, 302, 303), r.status_code

    def test_inversiones_ya_no_vive_dentro_de_cuentas(self):
        html = client.get("/cuentas").text
        self.assertFalse("Aportado neto" in html, "Cuentas sigue enseñando Inversiones")
        self.assertFalse("Histórico de valoraciones" in html,
                         "Cuentas sigue enseñando el histórico de valoraciones")

    def test_inversiones_tiene_lo_suyo(self):
        html = client.get("/inversiones").text
        self.assertTrue("Aportado neto" in html, "Inversiones no enseña el aportado neto")

    def test_las_reglas_de_transferencia_se_mudan_a_reglas(self):
        self.assertFalse("transferencias externas" in client.get("/cuentas").text.lower(),
                         "las reglas de transferencia siguen en Cuentas")
        self.assertTrue("transferencias externas" in client.get("/reglas").text.lower(),
                        "las reglas de transferencia no han llegado a Reglas")

    def test_las_urls_de_las_acciones_no_cambian(self):
        """Issue 1: las secciones conservan su URL, así que los POST también."""
        rutas = rutas_registradas()
        for path in ("/cuentas/nueva", "/cuentas/{account_id}/valoracion",
                     "/reglas-transferencias/nueva", "/conciliar/nueva"):
            with self.subTest(ruta=path):
                self.assertIn(path, rutas)


if __name__ == "__main__":
    unittest.main()
