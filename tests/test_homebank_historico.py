"""
Tests de la carga del histórico de HomeBank en una base de TNT: qué entra, con
qué categoría, y que no entra dos veces.

Lo que no puede fallar, porque el histórico entra detrás de datos que ya
cuadran con el banco:

- No se crea ninguna categoría: cada una de HomeBank va a la de TNT que diga
  la tabla de equivalencias, y si falta alguna, no se escribe nada.
- Un ajuste fija un movimiento concreto; si casa con dos, no se escribe nada.
- El mismo ejercicio no se carga dos veces.

Los traspasos y los saldos están en test_homebank_historico_saldos.py. Datos
inventados, los de base_homebank_historico.py.
"""
import os
import tempfile
import unittest
from datetime import date

from app.db import cursor
from app.importers import homebank_xhb
from app.services import homebank_historico as hh
from tests.base_homebank_historico import BaseHistorico, D


class TestCarga(BaseHistorico):
    def test_cada_movimiento_del_ejercicio_en_su_cuenta(self):
        r = self._cargar()
        a, b, f = self.tnt
        nuevas = self._filas("hash LIKE 'homebank:2025:%'")
        por_cuenta = {c: sum(1 for x in nuevas if x["account_id"] == c) for c in self.tnt}
        # A: 7 de HomeBank + la discrepancia; B: 2; fondo: el de 2025 y la corrección de 2026.
        self.assertEqual(por_cuenta, {a: 8, b: 2, f: 2})
        self.assertEqual(r.por_cuenta, {a: 7, b: 2, f: 1})
        self.assertFalse(any(x["date"] < "2025-01-01" for x in nuevas))

    def test_la_nota_y_la_categoria_de_homebank_se_conservan(self):
        self._cargar()
        cena = self._filas("description = 'Pago en RESTAURANTE SOL'")[0]
        self.assertEqual((cena["memo"], cena["source_hint"]), ("Cena con amigos", "Comida"))

    def test_sin_descripcion_toma_el_nombre_de_su_categoria(self):
        self._cargar()
        self.assertEqual(len(self._filas("description = 'Intereses' AND amount = 10")), 1)

    def test_no_se_crea_ninguna_categoria(self):
        self._cargar()
        with cursor() as cur:
            self.assertEqual(cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
                             self.categorias_antes)


class TestCategorias(BaseHistorico):
    def _categoria(self, descripcion):
        return self._filas("description = ?", (descripcion,))[0]["category_id"]

    def test_fija(self):
        self._cargar()
        self.assertEqual(self._categoria("NOMINA"), self.cat["nomina"])

    def test_segun_el_movimiento_solo_acepta_lo_permitido(self):
        self._cargar()
        self.assertEqual(self._categoria("Pago en RESTAURANTE SOL"), self.cat["restaurante"])
        self.assertEqual(self._categoria("Pago en MERCADO"), self.cat["super"])
        # La regla de Bizum diría «Bizum enviado», que aquí no se acepta.
        self.assertEqual(self._categoria("BIZUM ENVIADO"), self.cat["super"])

    def test_las_reglas_casan_por_palabra_entera(self):
        # El mismo criterio que al importar: por subcadena, «SOL» casaba
        # dentro de «GIRASOLES» y se llevaba la compra a restaurantes.
        with cursor() as cur:
            cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                        "VALUES ('SOL', ?, 100, 'manual', 1)", (self.cat["restaurante"],))
        self.libro.operaciones.append(homebank_xhb.OperacionHB(
            900, date(2025, 2, 6), D("-12.00"), 1, "Comida", "Pago en GIRASOLES", "", False))
        self._cargar()
        self.assertEqual(self._categoria("Pago en GIRASOLES"), self.cat["super"])
        self.assertEqual(self._categoria("Pago en RESTAURANTE SOL"), self.cat["restaurante"])

    def test_una_categoria_sin_equivalencia_no_escribe_nada(self):
        plan = self._plan()
        del plan.equivalencias["Ahorro"]
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "Ahorro"):
                hh.cargar(cur, self.libro, plan)
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])

    def test_leer_equivalencias_rechaza_un_destino_que_no_existe(self):
        fd, ruta = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8-sig") as fh:
            fh.write("HomeBank;Propuesta en TNT;Cómo;Acepta de las reglas\n"
                     "Comida;Alimentación › No existe;fija;\n")
        self.addCleanup(os.remove, ruta)
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "No existe"):
                hh.leer_equivalencias(cur, ruta)

    def test_categoria_por_ruta(self):
        with cursor() as cur:
            self.assertEqual(hh.categoria_por_ruta(cur, " Alimentación › Supermercados y alimentación "),
                             self.cat["super"])
            self.assertIsNone(hh.categoria_por_ruta(cur, hh.SIN_CATEGORIA))
            with self.assertRaisesRegex(ValueError, "«Inventada»"):
                hh.categoria_por_ruta(cur, "Inventada")


class TestUnaSolaVez(BaseHistorico):
    def test_no_se_carga_dos_veces(self):
        self._cargar()
        with self.assertRaisesRegex(ValueError, "ya"):
            self._cargar()
        self.assertEqual(len(self._filas("description = 'NOMINA'")), 1)


class TestAjustes(BaseHistorico):
    """Un ajuste fija un movimiento concreto de HomeBank. Dos cuotas iguales
    el mismo día en la misma cuenta se distinguen por la descripción."""

    def _gemelos(self):
        self.libro.operaciones.extend(
            homebank_xhb.OperacionHB(900 + i, date(2025, 11, 27), D("625.00"), 1, "Comida", texto, "", False)
            for i, texto in enumerate(("Cuota octubre", "Cuota noviembre")))

    def _categoria(self, descripcion):
        return self._filas("description = ?", (descripcion,))[0]["category_id"]

    def test_dos_iguales_el_mismo_dia_se_distinguen_por_la_descripcion(self):
        self._gemelos()
        ajuste = hh.Ajuste(1, date(2025, 11, 27), D("625.00"), self.cat["otros_ingresos"], False, "Cuota octubre")
        self._cargar(ajustes=self._plan().ajustes + (ajuste,))
        self.assertEqual(self._categoria("Cuota octubre"), self.cat["otros_ingresos"])
        self.assertEqual(self._categoria("Cuota noviembre"), self.cat["super"])

    def test_sin_descripcion_el_que_casa_con_dos_no_escribe_nada(self):
        self._gemelos()
        ajuste = hh.Ajuste(1, date(2025, 11, 27), D("625.00"), self.cat["otros_ingresos"], False)
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "casa con 2"):
                hh.cargar(cur, self.libro, self._plan(ajustes=self._plan().ajustes + (ajuste,)))
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])


if __name__ == "__main__":
    unittest.main()
