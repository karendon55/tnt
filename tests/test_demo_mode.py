"""
Tests del modo demostración y de lo que /health cuenta de sí mismo.

Lo que motiva este fichero: el lanzador reutiliza cualquier servidor que
responda 200 en el puerto. Un servidor de desarrollo apuntando a la base de
mentira también responde 200, así que TNT se abría mostrando movimientos
inventados como si fueran los del usuario. Ahora /health dice qué base sirve,
el lanzador compara, y la interfaz lo avisa por su cuenta.
"""
import unittest

from app.main import health
from app.templating import templates


class TestHealth(unittest.TestCase):
    def test_dice_que_base_sirve(self):
        """Sin este dato, el lanzador no puede distinguir un TNT de otro."""
        h = health()
        self.assertEqual(h["status"], "ok")
        self.assertIn("db", h)
        self.assertTrue(h["db"].endswith(".db"), h["db"])

    def test_dice_si_es_demostracion(self):
        h = health()
        self.assertIn("demo", h)
        self.assertIsInstance(h["demo"], bool)


class TestAvisoEnLaInterfaz(unittest.TestCase):
    def render_base(self, demo: bool) -> str:
        tpl = templates.get_template("base.html")
        return tpl.render(demo_mode=demo, app_name="TNT", app_tagline="Tus Números Tranquilos")

    def test_con_demo_la_barra_lo_avisa(self):
        self.assertIn("Datos de demostración", self.render_base(True))

    def test_sin_demo_no_hay_aviso(self):
        self.assertNotIn("Datos de demostración", self.render_base(False))


if __name__ == "__main__":
    unittest.main()
