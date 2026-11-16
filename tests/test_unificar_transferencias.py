"""
Tests de la unificación de «Transferencias» con el árbol de ING.

TNT sembraba «Transferencias › Traspaso entre cuentas», y las importaciones de
ING traen el suyo: «Otros gastos › Transferencias» para el dinero que va a
otras personas y «Movimientos excluidos › Traspaso entre cuentas» para el que
va entre cuentas propias. Decidido por el usuario: se queda el de ING.

- Lo emparejado va a «Movimientos excluidos › Traspaso entre cuentas», y lo
  suelto que entra, con ello.
- Lo suelto que sale (la paga mensual) va a «Otros gastos › Transferencias»,
  con una regla manual para las próximas.
- Los ingresos y gastos de cada mes no cambian.
- Las reglas integradas y la siembra dejan de crear «Transferencias».
- Si no hay nada que unificar no hace nada, y si hay un presupuesto en las
  viejas no toca nada y lo dice.

Datos inventados.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-unificar-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "unificar.db")

from app.db import DEFAULT_CATEGORIES, cursor, init_db  # noqa: E402
from app.services import unificar_transferencias as ut  # noqa: E402
from app.services.analytics import month_income_expense  # noqa: E402
from app.services.categories import resolve_category  # noqa: E402
from app.services.categorizer import seed_builtin_rules  # noqa: E402

init_db()
ING_TRASPASO = "Movimientos excluidos › Traspaso entre cuentas"
ING_TRANSFERENCIAS = "Otros gastos › Transferencias"
_PATRONES = ("BIZUM", "TRASPASO", "TRASPASOS", "FONDO", "COMISIONES", "MI TRASPASO", "PAGO TRASPASOS")


def _ruta(cur, categoria):
    f = cur.execute("SELECT c.name, p.name FROM categories c LEFT JOIN categories p ON p.id = c.parent_id "
                    "WHERE c.id = ?", (categoria,)).fetchone()
    return None if f is None else (f"{f[1]} › {f[0]}" if f[1] else f[0])


class _Limpio(unittest.TestCase):
    """Cada test deja la base como la encontró: la comparten todos los
    ficheros cuando se lanzan juntos."""

    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
            cur.execute("DELETE FROM category_rules WHERE source = 'builtin'")  # cada importación las siembra

    def tearDown(self):
        with cursor() as cur:
            cur.execute("DELETE FROM accounts WHERE name LIKE 'Unificar %'")  # sus movimientos, en cascada
            cur.execute(f"DELETE FROM category_rules WHERE source = 'builtin' OR pattern IN "
                        f"({','.join('?' * len(_PATRONES))})", _PATRONES)
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM budgets WHERE category_id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")


class _Base(_Limpio):
    def setUp(self):
        super().setUp()
        with cursor() as cur:
            self.padre = resolve_category(cur, "Transferencias")
            self.hija = resolve_category(cur, "Transferencias|Traspaso entre cuentas")
            cuentas = []
            for nombre in ("Unificar A", "Unificar B"):
                cur.execute("INSERT INTO accounts(name, type) VALUES (?, 'bank')", (nombre,))
                cuentas.append(cur.lastrowid)
            a, b = cuentas

            def mov(cuenta, dia, importe, texto, categoria):
                cur.execute("INSERT INTO transactions(account_id, date, amount, description, category_id, hash) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (cuenta, f"2026-05-{dia:02d}", importe, texto, categoria, f"unificar-{dia}-{cuenta}"))
                return cur.lastrowid

            self.ida = mov(a, 2, -100, "Traspaso a B", self.hija)
            self.vuelta = mov(b, 2, 100, "Traspaso de A", self.hija)
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (self.vuelta, self.ida))
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (self.ida, self.vuelta))
            self.paga = mov(a, 3, -120, "PAGO TRASPASOS", self.hija)
            self.entra = mov(a, 4, 50, "TRASPASO RECIBIDO", self.hija)
            self.directo = mov(a, 5, -30, "Transferencia a un amigo", self.padre)
            for patron, categoria, fuente in (("BIZUM", self.padre, "builtin"), ("TRASPASO", self.hija, "builtin"),
                                              ("TRASPASOS", self.hija, "builtin"), ("FONDO", self.hija, "learned"),
                                              ("COMISIONES", self.padre, "learned"),
                                              ("MI TRASPASO", self.hija, "manual")):
                cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                            "VALUES (?, ?, 150, ?, 1)", (patron, categoria, fuente))
            self.kpis = month_income_expense(cur, "2026-05-01", "2026-05-31")

    def _unificar(self):
        with cursor() as cur:
            return ut.unificar(cur)

    def _categoria(self, movimiento):
        with cursor() as cur:
            return _ruta(cur, cur.execute("SELECT category_id FROM transactions WHERE id = ?",
                                          (movimiento,)).fetchone()[0])

    def _regla(self, patron):
        with cursor() as cur:
            return [(_ruta(cur, r[0]), r[1]) for r in cur.execute(
                "SELECT category_id, source FROM category_rules WHERE pattern = ?", (patron,))]


class TestUnificar(_Base):
    def test_lo_emparejado_y_lo_que_entra_van_al_traspaso_de_ing(self):
        self._unificar()
        for movimiento in (self.ida, self.vuelta, self.entra):
            self.assertEqual(self._categoria(movimiento), ING_TRASPASO)

    def test_lo_suelto_que_sale_va_a_transferencias_de_ing(self):
        self._unificar()
        self.assertEqual(self._categoria(self.paga), ING_TRANSFERENCIAS)
        self.assertEqual(self._categoria(self.directo), ING_TRANSFERENCIAS)

    def test_los_ingresos_y_gastos_del_mes_no_cambian(self):
        self._unificar()
        with cursor() as cur:
            self.assertEqual(month_income_expense(cur, "2026-05-01", "2026-05-31"), self.kpis)

    def test_las_reglas(self):
        self._unificar()
        self.assertEqual(self._regla("BIZUM"), [(ING_TRANSFERENCIAS, "builtin")])
        self.assertEqual(self._regla("TRASPASO"), [(ING_TRASPASO, "builtin")])
        self.assertEqual(self._regla("TRASPASOS"), [(ING_TRASPASO, "builtin")])
        # Las aprendidas se borran: la próxima importación las aprende de nuevo.
        # («COMISIONES» también es integrada, y esa sigue.)
        self.assertEqual([r for r in self._regla("FONDO") + self._regla("COMISIONES") if r[1] == "learned"], [])
        self.assertEqual(self._regla("MI TRASPASO"), [(ING_TRASPASO, "manual")])
        self.assertEqual(self._regla("PAGO TRASPASOS"), [(ING_TRANSFERENCIAS, "manual")])

    def test_desaparecen_las_viejas(self):
        self._unificar()
        with cursor() as cur:
            self.assertIsNone(_ruta(cur, self.padre))
            self.assertIsNone(_ruta(cur, self.hija))

    def test_resumen_y_la_segunda_vez_no_hace_nada(self):
        r = self._unificar()
        self.assertEqual((r.traspasos, r.sueltos, r.reglas_borradas), (3, 2, 2))
        self.assertIsNone(self._unificar())


class TestNoUnifica(_Base):
    def test_con_un_presupuesto_en_las_viejas_no_toca_nada(self):
        with cursor() as cur:
            cur.execute("INSERT INTO budgets(category_id, monthly_limit) VALUES (?, 100)", (self.padre,))
        with self.assertRaisesRegex(ValueError, "presupuesto"):
            self._unificar()
        self.assertEqual(self._categoria(self.paga), "Transferencias › Traspaso entre cuentas")
        self.assertEqual(self._regla("BIZUM"), [("Transferencias", "builtin")])


class TestLoQueSeSiembra(_Limpio):
    def test_las_categorias_por_defecto_no_traen_transferencias(self):
        self.assertNotIn("Transferencias", [nombre for nombre, _, _ in DEFAULT_CATEGORIES])

    def test_las_reglas_integradas_no_crean_transferencias(self):
        with cursor() as cur:
            seed_builtin_rules(cur)
            self.assertIsNone(cur.execute(
                "SELECT 1 FROM categories WHERE name = 'Transferencias' AND parent_id IS NULL").fetchone())
        self.assertEqual(TestUnificar._regla(self, "BIZUM"), [(ING_TRANSFERENCIAS, "builtin")])
        self.assertEqual(TestUnificar._regla(self, "TRASPASO"), [(ING_TRASPASO, "builtin")])


if __name__ == "__main__":
    unittest.main()
