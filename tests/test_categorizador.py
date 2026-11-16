"""
Tests del motor de categorización, por la parte que la pantalla de importación
enseña como cifra.

El caso que los motiva: tras importar 3 movimientos, el resultado decía
«Auto-categorizados: 71». No era un error de cuentas, era un rótulo mentiroso:
`apply_rules_to_uncategorized` recorre TODA la base, no solo lo que acaba de
entrar, así que el número mezclaba lo del fichero con movimientos viejos que
las reglas recién aprendidas rescataron de paso.

Las dos cifras son útiles, pero son cosas distintas y hay que poder separarlas.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-cat-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "cat.db")

from app.db import DEFAULT_CATEGORIES, cursor, init_db  # noqa: E402
from app.services.categories import resolve_category  # noqa: E402
from app.services.categorizer import (  # noqa: E402
    apply_rules_to_uncategorized, learn_rules_from_known, retrain_and_apply,
)

init_db()


def _cuenta(cur, nombre="Cuenta test"):
    cur.execute("INSERT INTO accounts(name, type) VALUES (?, 'bank')", (nombre,))
    return cur.lastrowid


def _categoria(cur, nombre):
    cur.execute("INSERT INTO categories(name, kind) VALUES (?, 'expense')", (nombre,))
    return cur.lastrowid


def _regla(cur, patron, cat_id, prioridad=150):
    cur.execute(
        "INSERT INTO category_rules(pattern, category_id, priority, hits, source)"
        " VALUES (?, ?, ?, 0, 'manual')", (patron, cat_id, prioridad))


def _movimiento(cur, cuenta, desc, hash_, batch=None, cat=None):
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, hash,"
        " import_batch_id, category_id) VALUES (?, '2026-08-01', -10.0, ?, ?, ?, ?)",
        (cuenta, desc, hash_, batch, cat))
    return cur.lastrowid


class TestAplicarReglas(unittest.TestCase):
    def test_categoriza_lo_que_encaja_y_deja_lo_demas(self):
        with cursor() as cur:
            c = _cuenta(cur, "c1")
            cat = _categoria(cur, "Cat A")
            _regla(cur, "MERCADO", cat)
            encaja = _movimiento(cur, c, "COMPRA EN MERCADO CENTRAL", "h1")
            no_encaja = _movimiento(cur, c, "OTRA COSA", "h2")

            total, _ = apply_rules_to_uncategorized(cur)

            self.assertGreaterEqual(total, 1)
            filas = {r["id"]: r["category_id"] for r in cur.execute(
                "SELECT id, category_id FROM transactions WHERE id IN (?, ?)",
                (encaja, no_encaja))}
        self.assertEqual(filas[encaja], cat)
        self.assertIsNone(filas[no_encaja])

    def test_no_toca_lo_que_ya_tenia_categoria(self):
        with cursor() as cur:
            c = _cuenta(cur, "c2")
            cat_a = _categoria(cur, "Cat B")
            cat_b = _categoria(cur, "Cat C")
            _regla(cur, "PANADERIA", cat_a)
            ya = _movimiento(cur, c, "PANADERIA LA ESPIGA", "h3", cat=cat_b)

            apply_rules_to_uncategorized(cur)

            actual = cur.execute(
                "SELECT category_id FROM transactions WHERE id = ?", (ya,)).fetchone()
        self.assertEqual(actual["category_id"], cat_b,
                         "una regla pisó una categoría ya asignada")

    def test_separa_lo_del_lote_de_lo_que_ya_estaba(self):
        """La cifra que la pantalla de importación necesita saber partir."""
        with cursor() as cur:
            c = _cuenta(cur, "c3")
            cat = _categoria(cur, "Cat D")
            _regla(cur, "FERRETERIA", cat)
            cur.execute("INSERT INTO import_batches(files, inserted, duplicates)"
                        " VALUES ('[]', 0, 0)")
            lote = cur.lastrowid
            # dos del lote que acaba de entrar…
            _movimiento(cur, c, "FERRETERIA UNO", "h4", batch=lote)
            _movimiento(cur, c, "FERRETERIA DOS", "h5", batch=lote)
            # …y tres viejos que estaban sin categoría
            for i in range(3):
                _movimiento(cur, c, f"FERRETERIA VIEJA {i}", f"h6{i}")

            total, del_lote = apply_rules_to_uncategorized(cur, batch_id=lote)

        self.assertEqual(total, 5, "no categorizó todo lo que encajaba")
        self.assertEqual(del_lote, 2, "no separó bien lo que venía en el lote")

    def test_sin_lote_no_se_atribuye_nada(self):
        with cursor() as cur:
            c = _cuenta(cur, "c4")
            cat = _categoria(cur, "Cat E")
            _regla(cur, "ZAPATERIA", cat)
            _movimiento(cur, c, "ZAPATERIA CENTRO", "h7")

            total, del_lote = apply_rules_to_uncategorized(cur)

        self.assertGreaterEqual(total, 1)
        self.assertEqual(del_lote, 0)


class TestRetrainAndApply(unittest.TestCase):
    def test_devuelve_las_tres_cifras(self):
        with cursor() as cur:
            cur.execute("INSERT INTO import_batches(files, inserted, duplicates)"
                        " VALUES ('[]', 0, 0)")
            lote = cur.lastrowid
            creadas, total, del_lote = retrain_and_apply(cur, batch_id=lote)
        self.assertIsInstance(creadas, int)
        self.assertIsInstance(total, int)
        self.assertIsInstance(del_lote, int)
        self.assertLessEqual(del_lote, total,
                             "lo del lote no puede ser más que el total")


class TestElHistoricoNoEnsenaReglas(unittest.TestCase):
    """Lo cargado del histórico de HomeBank (huella «homebank:…») ni enseña
    reglas ni quita las que hay: sus categorías salen de una tabla de
    equivalencias, no de cómo categoriza el usuario hoy. Con él, TNT tiene
    que seguir categorizando igual que antes de cargarlo."""

    def setUp(self):
        with cursor() as cur:
            self.cuenta = _cuenta(cur, "historico")
            self.fruta = _categoria(cur, "Fruta del histórico")
            self.bar = _categoria(cur, "Bar del histórico")
            for i in range(3):
                _movimiento(cur, self.cuenta, "FRUTERIA PEPA", f"hist-hoy-{i}", cat=self.fruta)

    def tearDown(self):
        with cursor() as cur:  # los movimientos y las reglas se van en cascada
            cur.execute("DELETE FROM accounts WHERE id = ?", (self.cuenta,))
            cur.execute("DELETE FROM categories WHERE id IN (?, ?)", (self.fruta, self.bar))

    def _aprender(self, filas=()):
        with cursor() as cur:
            for desc, huella, cat in filas:
                _movimiento(cur, self.cuenta, desc, huella, cat=cat)
            learn_rules_from_known(cur)

    @staticmethod
    def _reglas(patron):
        with cursor() as cur:
            return [r[0] for r in cur.execute(
                "SELECT category_id FROM category_rules WHERE pattern = ? AND source = 'learned'", (patron,))]

    def test_lo_de_hoy_si_ensena(self):
        self._aprender([("VERMUTERIA LOLA", f"hist-v-{i}", self.bar) for i in range(3)])
        self.assertEqual(self._reglas("VERMUTERIA"), [self.bar])

    def test_el_historico_no_crea_reglas(self):
        self._aprender([("VERMUTERIA LOLA", f"homebank:2025:v-{i}", self.bar) for i in range(3)])
        self.assertEqual(self._reglas("VERMUTERIA"), [])

    def test_el_historico_no_quita_las_que_hay(self):
        self._aprender()
        self.assertEqual(self._reglas("FRUTERIA"), [self.fruta])
        # En 2025 la misma frutería iba a otra categoría: manda cómo se categoriza hoy.
        self._aprender([("FRUTERIA PEPA", f"homebank:2025:f-{i}", self.bar) for i in range(5)])
        self.assertEqual(self._reglas("FRUTERIA"), [self.fruta])



class TestCategoriasRepetidas(unittest.TestCase):
    """«Transporte público» y «Deporte y gimnasio» estaban repetidas: la que
    siembra TNT y la del árbol de ING. Decidido por el usuario: el transporte
    público va a «Transporte» y el gimnasio a «Educación y salud»."""

    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}

    def tearDown(self):
        with cursor() as cur:
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def test_el_transporte_publico_de_ing_va_al_de_transporte(self):
        # ING lo manda a veces bajo «Vehículo y transporte»; sin traducirlo, cada
        # importación volvería a crear la repetida.
        with cursor() as cur:
            destino = resolve_category(cur, "Transporte|Transporte público")
            self.assertEqual(resolve_category(cur, "Vehículo y transporte|Transporte público"), destino)
            self.assertIsNone(cur.execute(
                "SELECT 1 FROM categories c JOIN categories p ON p.id = c.parent_id "
                "WHERE p.name = 'Vehículo y transporte' AND c.name = 'Transporte público'").fetchone())

    def test_la_siembra_no_trae_el_gimnasio_en_ocio(self):
        hijas = {nombre: subs for nombre, _, subs in DEFAULT_CATEGORIES}
        self.assertNotIn("Deporte y gimnasio", hijas["Ocio y viajes"])


if __name__ == "__main__":
    unittest.main()
