"""
Tests del cálculo de la declaración de la Renta (app/services/renta.py).

La sección no guarda importes: todo sale de los movimientos clasificados en
las categorías del piso alquilado. Aquí se fija lo que no puede fallar en un
total que va a Hacienda: que sume exacto al céntimo, que un ejercicio no se
mezcle con el de al lado, que los dos seguros vayan separados, que cada
concepto cuadre con su detalle, y que lo del otro piso no se cuele.

El piso es inventado («Calle Ejemplo»): ni direcciones ni importes reales en
el repositorio. La base es temporal y propia, pero `unittest discover`
comparte proceso con otros ficheros: cada test limpia al entrar y al salir,
también las categorías que crea.
"""
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-renta-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "renta.db")

from app.db import cursor, init_db  # noqa: E402
from app.services import renta  # noqa: E402
from app.services.categories import resolve_category  # noqa: E402

init_db()

D = Decimal
INMUEBLE = "Calle Ejemplo"


class _Base(unittest.TestCase):
    """Un año de alquiler inventado, con trampas en los bordes."""

    def setUp(self):
        with cursor() as cur:
            self._categorias_previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        with cursor() as cur:
            renta.cargar_ajustes(cur)
            self.aj = renta.guardar_ajustes(cur, INMUEBLE, ["TGR"])
            self.cat = self.aj.categorias
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
            self.cuenta = cur.lastrowid
            cur.execute("INSERT INTO accounts(name, type, archived) VALUES ('Vieja', 'bank', 1)")
            self.vieja = cur.lastrowid
            impuestos = resolve_category(cur, "Impuestos y comisiones|Impuestos")
            seguros_hogar = resolve_category(cur, "Hogar|Seguros del hogar")
            garaje = resolve_category(cur, "Alquiler|Garaje", default_kind="income")
            m = lambda *a, **k: self._mov(cur, *a, **k)  # noqa: E731

            # Ingresos: 4 × 820 + 60 (subcategoría) − 820 (devolución) = 2.520,00
            self.alq_enero = m("2026-01-01", 820.00, self.cat["ingresos"], "Alquiler enero 26")
            m("2026-02-01", 820.00, self.cat["ingresos"], "Alquiler febrero 26", cuenta=self.vieja)
            traspaso = m("2026-03-01", 820.00, self.cat["ingresos"], "Traspaso interno recibido Alquiler marzo 26")
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (traspaso, traspaso))
            m("2026-04-01", 60.00, garaje, "Alquiler plaza de garaje")
            m("2026-05-03", -820.00, self.cat["ingresos"], "Devolución alquiler mayo")
            m("2026-12-31", 820.00, self.cat["ingresos"], "Alquiler diciembre 26")
            # Los vecinos de los bordes, que no pueden colarse en 2026.
            m("2025-12-31", 900.00, self.cat["ingresos"], "Alquiler diciembre 25")
            m("2027-01-01", 1000.00, self.cat["ingresos"], "Alquiler enero 27")

            # Seguros: impago 412,36; vivienda 158,41 − 10,00 de extorno = 148,41
            self.impago = m("2026-02-04", -412.36, self.cat["impago"], "ASEGURADORA EJEMPLO", nota="Impago Calle Ejemplo")
            self.vivienda = m("2026-05-20", -158.41, self.cat["vivienda"], "CORREDURIA EJEMPLO")
            m("2026-06-01", 10.00, self.cat["vivienda"], "Extorno seguro")
            # IBI: 61,17 + 61,17 + 61,15 = 183,49
            for fecha, imp in (("2026-01-05", -61.17), ("2026-04-07", -61.17), ("2026-07-06", -61.15)):
                m(fecha, imp, self.cat["ibi"], "Recibo Ayuntamiento", nota="IBI Calle Ejemplo")
            # Comunidad: 3 × 142,80 − 19,40 de devolución = 409,00
            for fecha in ("2026-01-05", "2026-04-01", "2026-07-01"):
                m(fecha, -142.80, self.cat["comunidad"], "Recibo C.P. CALLE EJEMPLO 18")
            m("2026-01-16", 19.40, self.cat["comunidad"], "Devolución de recibo C.P. CALLE EJEMPLO")

            # Lo que no es del piso o no está clasificado.
            self.otro_piso = m("2026-05-20", -231.50, seguros_hogar, "OTRA ASEGURADORA", nota="Seguro Otra Calle")
            self.ibi_mal = m("2026-10-05", -61.17, impuestos, "Recibo Ayuntamiento", nota="IBI Cálle Ejémplo")
            self.tgr = m("2026-01-05", -5.90, impuestos, "Recibo Ayuntamiento", nota="TGR Calle Ejemplo")
            self.fontanero = m("2026-08-01", -45.00, None, "FONTANERIA CALLE EJEMPLO 18")
            self.en_el_padre = m("2026-09-01", -30.00, self.cat["padre"], "Cerrajero")
            self.dni = m("2026-03-31", -30.00, impuestos, "DNI")
            self.arreglo_2025 = m("2025-06-01", -20.00, None, "Arreglo Calle Ejemplo")

    def tearDown(self):
        self._vaciar()

    def _vaciar(self):
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))
            previas = ",".join(str(i) for i in self._categorias_previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def _mov(self, cur, fecha, importe, categoria, descripcion, nota=None, cuenta=None):
        cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description, memo, category_id, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cuenta or self.cuenta, fecha, importe, descripcion, nota, categoria,
             f"renta-{fecha}-{descripcion}-{importe}-{nota}"))
        return cur.lastrowid

    def _informe(self, ejercicio=2026):
        with cursor() as cur:
            return renta.informe(cur, ejercicio, renta.cargar_ajustes(cur))


class TestTotales(_Base):
    def test_ingresos_con_devolucion_subcategoria_cuenta_archivada_y_traspaso(self):
        self.assertEqual(self._informe().apartados["ingresos"].total, D("2520.00"))

    def test_cada_gasto_su_total(self):
        ap = self._informe().apartados
        self.assertEqual(ap["impago"].total, D("412.36"))
        self.assertEqual(ap["vivienda"].total, D("148.41"))
        self.assertEqual(ap["ibi"].total, D("183.49"))
        self.assertEqual(ap["comunidad"].total, D("409.00"))

    def test_los_seguros_van_separados_y_suman_aparte(self):
        inf = self._informe()
        impago = {l.id for l in inf.apartados["impago"].lineas}
        vivienda = {l.id for l in inf.apartados["vivienda"].lineas}
        self.assertEqual(impago, {self.impago})
        self.assertIn(self.vivienda, vivienda)
        self.assertFalse(impago & vivienda)
        self.assertEqual(inf.total_seguros, D("560.77"))

    def test_cada_concepto_cuadra_con_su_detalle(self):
        for clave, ap in self._informe().apartados.items():
            with self.subTest(concepto=clave):
                self.assertTrue(ap.lineas, "un concepto sin detalle")
                suma = sum((l.importe for l in ap.lineas), D("0"))
                self.assertEqual(ap.total, suma if ap.concepto.es_ingreso else -suma)

    def test_lo_del_otro_piso_no_entra(self):
        for clave, ap in self._informe().apartados.items():
            with self.subTest(concepto=clave):
                self.assertNotIn(self.otro_piso, {l.id for l in ap.lineas})

    def test_el_detalle_conserva_el_signo_del_banco(self):
        importes = [l.importe for l in self._informe().apartados["comunidad"].lineas]
        self.assertIn(D("19.40"), importes)
        self.assertIn(D("-142.80"), importes)


class TestEjercicios(_Base):
    def test_no_se_mezclan_los_anios(self):
        for anio, total in ((2025, D("900.00")), (2026, D("2520.00")), (2027, D("1000.00"))):
            with self.subTest(ejercicio=anio):
                ingresos = self._informe(anio).apartados["ingresos"]
                self.assertEqual(ingresos.total, total)
                self.assertTrue(all(l.fecha.startswith(str(anio)) for l in ingresos.lineas))

    def test_un_anio_sin_movimientos_da_ceros_sin_detalle(self):
        for clave, ap in self._informe(2019).apartados.items():
            with self.subTest(concepto=clave):
                self.assertEqual((ap.total, ap.lineas), (D("0"), []))

    def test_anios_disponibles(self):
        with cursor() as cur:
            self.assertEqual(renta.ejercicios(cur, date(2026, 10, 7)), [2027, 2026, 2025])
            self.assertEqual(renta.ejercicios(cur, date(2030, 1, 15)), [2030, 2029, 2027, 2026, 2025])

    def test_ejercicio_por_defecto_sigue_la_campania(self):
        # Hasta junio se prepara la declaración del año anterior.
        for hoy, esperado in ((date(2027, 4, 15), 2026), (date(2026, 6, 30), 2025),
                              (date(2026, 7, 1), 2026), (date(2026, 10, 7), 2026)):
            with self.subTest(hoy=hoy):
                self.assertEqual(renta.ejercicio_por_defecto(hoy), esperado)


class TestCentimos(_Base):
    def test_suma_exacta_donde_la_coma_flotante_falla(self):
        self.assertNotEqual(0.10 + 0.20, 0.30)  # lo que evita el Decimal
        with cursor() as cur:
            self._mov(cur, "2024-03-01", -0.10, self.cat["ibi"], "Recibo")
            self._mov(cur, "2024-06-01", -0.20, self.cat["ibi"], "Recibo")
        self.assertEqual(self._informe(2024).apartados["ibi"].total, D("0.30"))

    def test_cada_importe_a_centimos(self):
        self.assertEqual(renta.centimos(61.17), D("61.17"))
        self.assertEqual(renta.centimos(-0.1), D("-0.10"))
        self.assertEqual(renta.centimos(1250), D("1250.00"))


class TestPorRevisar(_Base):
    def test_lo_que_menciona_el_piso_sin_clasificar_y_lo_que_cuelga_del_padre(self):
        ids = [l.id for l in self._informe().por_revisar]
        # Por fecha: fontanero (1/8), cerrajero en el padre (1/9), IBI mal puesto (5/10).
        self.assertEqual(ids, [self.fontanero, self.en_el_padre, self.ibi_mal])

    def test_sin_tildes_ni_mayusculas(self):
        ids = {l.id for l in self._informe().por_revisar}
        self.assertIn(self.ibi_mal, ids)     # «Cálle Ejémplo»
        self.assertIn(self.fontanero, ids)   # «CALLE EJEMPLO»

    def test_las_palabras_ignoradas_salen_de_la_lista(self):
        self.assertNotIn(self.tgr, {l.id for l in self._informe().por_revisar})
        with cursor() as cur:
            renta.guardar_ajustes(cur, INMUEBLE, [])
        self.assertIn(self.tgr, {l.id for l in self._informe().por_revisar})

    def test_lo_clasificado_y_lo_ajeno_no_aparece(self):
        ids = {l.id for l in self._informe().por_revisar}
        for ajeno in (self.impago, self.otro_piso, self.dni, self.arreglo_2025):
            with self.subTest(movimiento=ajeno):
                self.assertNotIn(ajeno, ids)

    def test_cada_anio_revisa_lo_suyo(self):
        self.assertEqual([l.id for l in self._informe(2025).por_revisar], [self.arreglo_2025])

    def test_sin_nombre_solo_revisa_lo_del_padre(self):
        with cursor() as cur:
            renta.guardar_ajustes(cur, "", ["TGR"])
        inf = self._informe()
        self.assertFalse(inf.revision_por_nombre)
        self.assertEqual([l.id for l in inf.por_revisar], [self.en_el_padre])

    def test_los_totales_no_dependen_de_la_revision(self):
        antes = {c: ap.total for c, ap in self._informe().apartados.items()}
        with cursor() as cur:
            renta.guardar_ajustes(cur, "", [])
        despues = {c: ap.total for c, ap in self._informe().apartados.items()}
        self.assertEqual(antes, despues)


class TestCategorias(_Base):
    def test_se_crean_una_sola_vez(self):
        with cursor() as cur:
            primera = renta.cargar_ajustes(cur).categorias
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))
            segunda = renta.cargar_ajustes(cur).categorias
            padres = cur.execute(
                "SELECT COUNT(*) FROM categories WHERE name = 'Inmueble alquilado'").fetchone()[0]
        self.assertEqual(primera, segunda)
        self.assertEqual(padres, 1)

    def test_los_ingresos_van_en_una_categoria_de_ingresos(self):
        with cursor() as cur:
            kind = cur.execute("SELECT kind FROM categories WHERE id = ?",
                               (self.cat["ingresos"],)).fetchone()[0]
        self.assertEqual(kind, "income")

    def test_reutiliza_una_categoria_alquiler_que_ya_existia(self):
        # Como en la base real: «Alquiler» la creó el usuario, no el módulo,
        # y puede estar escrita con otras mayúsculas.
        with cursor() as cur:
            cur.execute("UPDATE categories SET name = 'ALQUILER' WHERE id = ?", (self.cat["ingresos"],))
            cur.execute("DELETE FROM settings WHERE key = ?", (renta.CLAVE_AJUSTES,))
            aj = renta.cargar_ajustes(cur)
            cuantas = cur.execute("SELECT COUNT(*) FROM categories WHERE parent_id IS NULL "
                                  "AND LOWER(name) = 'alquiler'").fetchone()[0]
        self.assertEqual(aj.categorias["ingresos"], self.cat["ingresos"])
        self.assertEqual(cuantas, 1)

    def test_renombrar_una_categoria_no_rompe_nada(self):
        with cursor() as cur:
            cur.execute("UPDATE categories SET name = 'IBI del piso' WHERE id = ?", (self.cat["ibi"],))
        ibi = self._informe().apartados["ibi"]
        self.assertEqual((ibi.total, ibi.falta_categoria), (D("183.49"), False))

    def test_borrar_una_categoria_se_avisa_y_sus_recibos_pasan_a_revision(self):
        with cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = ?", (self.cat["ibi"],))
        inf = self._informe()
        self.assertTrue(inf.apartados["ibi"].falta_categoria)
        self.assertFalse(inf.apartados["impago"].falta_categoria)
        # Los tres recibos se quedan sin categoría y mencionan el piso.
        self.assertEqual(len(inf.por_revisar), 3 + 3)

    def test_reparar_vuelve_a_crear_lo_que_falta(self):
        with cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = ?", (self.cat["ibi"],))
            nuevas = renta.reparar_categorias(cur).categorias
            existe = cur.execute("SELECT parent_id FROM categories WHERE id = ?", (nuevas["ibi"],)).fetchone()
        self.assertNotEqual(nuevas["ibi"], self.cat["ibi"])
        self.assertEqual(existe["parent_id"], self.cat["padre"])
        self.assertFalse(self._informe().apartados["ibi"].falta_categoria)
        self.assertEqual(nuevas["impago"], self.cat["impago"])


class TestAjustes(_Base):
    def test_guardar_limpia_espacios_vacios_y_repetidos(self):
        with cursor() as cur:
            aj = renta.guardar_ajustes(cur, "  Calle Ejemplo  ", [" TGR ", "", "tgr", "Basuras"])
        self.assertEqual(aj.inmueble, "Calle Ejemplo")
        self.assertEqual(aj.ignorar, ("TGR", "Basuras"))
        self.assertEqual(aj.categorias, self.cat)

    def test_unos_ajustes_rotos_no_tumban_la_seccion(self):
        with cursor() as cur:
            cur.execute("UPDATE settings SET value = 'no es json' WHERE key = ?", (renta.CLAVE_AJUSTES,))
            aj = renta.cargar_ajustes(cur)
        # Las categorías se recuperan por su nombre, sin duplicarse.
        self.assertEqual(aj.categorias, self.cat)
        self.assertEqual(self._informe().apartados["ibi"].total, D("183.49"))

    def test_normalizar(self):
        self.assertEqual(renta.normalizar("Cálle  Ejémplo "), "CALLE EJEMPLO")
        self.assertEqual(renta.normalizar(None), "")


if __name__ == "__main__":
    unittest.main()
