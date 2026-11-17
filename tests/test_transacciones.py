"""
Tests de atomicidad: una petición que escribe, o entra entera o no entra.

La conexión va en autocommit (`isolation_level=None`), así que cada sentencia
se confirma sola. Sin transacción, un fallo a mitad deja la mitad del cambio
escrita, y en una app de dinero eso significa cosas como un movimiento espejo
sin su enlace: un ingreso que aparece de la nada en el saldo, sin traspaso que
lo justifique.

La garantía vive en `cursor()`: cada bloque `with cursor() as cur:` es una
transacción. Así no hay que acordarse en cada uno de los cincuenta y cinco
sitios que lo usan.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-tx-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "tx.db")

from app.db import cursor, init_db, savepoint  # noqa: E402

init_db()


def cuenta_filas(tabla: str = "categories") -> int:
    with cursor() as cur:
        return cur.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]


class CursorQueFallaAlaNesima:
    """Envuelve un cursor real y revienta en la n-ésima escritura.

    Sirve para comprobar que una función que escribe dos veces no deja la
    primera hecha si la segunda falla."""

    def __init__(self, cur, fallar_en: int):
        self._cur = cur
        self._fallar_en = fallar_en
        self._escrituras = 0

    def execute(self, sql, *args, **kwargs):
        if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            self._escrituras += 1
            if self._escrituras == self._fallar_en:
                raise RuntimeError("fallo simulado a mitad de la escritura")
        return self._cur.execute(sql, *args, **kwargs)

    def __getattr__(self, nombre):
        return getattr(self._cur, nombre)


class TestCursorEsTransaccion(unittest.TestCase):
    def test_lo_escrito_se_confirma_al_salir(self):
        antes = cuenta_filas()
        with cursor() as cur:
            cur.execute("INSERT INTO categories(name, kind) VALUES ('tx-ok', 'expense')")
        self.assertEqual(cuenta_filas(), antes + 1)

    def test_una_excepcion_deshace_todo_lo_del_bloque(self):
        antes = cuenta_filas()
        with self.assertRaises(RuntimeError):
            with cursor() as cur:
                cur.execute("INSERT INTO categories(name, kind) VALUES ('tx-a', 'expense')")
                cur.execute("INSERT INTO categories(name, kind) VALUES ('tx-b', 'expense')")
                raise RuntimeError("algo salió mal después de escribir")
        self.assertEqual(cuenta_filas(), antes,
                         "quedaron filas de un bloque que falló")

    def test_la_excepcion_sigue_subiendo(self):
        """Deshacer no es tragarse el error: quien llama tiene que enterarse."""
        with self.assertRaises(ValueError):
            with cursor() as cur:
                cur.execute("INSERT INTO categories(name, kind) VALUES ('tx-c', 'expense')")
                raise ValueError("hola")


class TestSavepoint(unittest.TestCase):
    """Para trabajos por lotes: que un elemento malo no tire los buenos."""

    def test_lo_de_dentro_se_deshace_y_lo_de_fuera_se_queda(self):
        antes = cuenta_filas()
        with cursor() as cur:
            cur.execute("INSERT INTO categories(name, kind) VALUES ('sp-fuera', 'expense')")
            try:
                with savepoint(cur, "uno"):
                    cur.execute("INSERT INTO categories(name, kind) VALUES ('sp-dentro', 'expense')")
                    raise RuntimeError("este elemento del lote falla")
            except RuntimeError:
                pass
        self.assertEqual(cuenta_filas(), antes + 1)
        with cursor() as cur:
            nombres = {r["name"] for r in cur.execute(
                "SELECT name FROM categories WHERE name LIKE 'sp-%'")}
        self.assertIn("sp-fuera", nombres)
        self.assertNotIn("sp-dentro", nombres)

    def test_sin_error_el_savepoint_confirma(self):
        with cursor() as cur:
            with savepoint(cur, "dos"):
                cur.execute("INSERT INTO categories(name, kind) VALUES ('sp-bien', 'expense')")
        with cursor() as cur:
            n = cur.execute(
                "SELECT COUNT(*) AS n FROM categories WHERE name = 'sp-bien'").fetchone()["n"]
        self.assertEqual(n, 1)


class TestEmparejarTraspasoEsAtomico(unittest.TestCase):
    """El caso real: enlazar un traspaso son dos UPDATE, uno por lado."""

    def _dos_movimientos(self, cur):
        cur.execute("INSERT INTO accounts(name, type) VALUES ('A', 'bank')")
        a = cur.lastrowid
        cur.execute("INSERT INTO accounts(name, type) VALUES ('B', 'bank')")
        b = cur.lastrowid
        cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description, hash)"
            " VALUES (?, '2026-08-01', -100.0, 'salida', ?)", (a, f"h-out-{a}"))
        izq = cur.lastrowid
        cur.execute(
            "INSERT INTO transactions(account_id, date, amount, description, hash)"
            " VALUES (?, '2026-08-01', 100.0, 'entrada', ?)", (b, f"h-in-{b}"))
        return izq, cur.lastrowid

    def test_si_falla_el_segundo_lado_no_queda_el_primero(self):
        from app.routers.transfers import _link_pair

        with cursor() as cur:
            izq, der = self._dos_movimientos(cur)

        with self.assertRaises(RuntimeError):
            with cursor() as cur:
                # la 2ª escritura es el enlace del segundo lado
                _link_pair(CursorQueFallaAlaNesima(cur, fallar_en=2), izq, der)

        with cursor() as cur:
            enlaces = [r["transfer_id"] for r in cur.execute(
                "SELECT transfer_id FROM transactions WHERE id IN (?, ?)", (izq, der))]
        self.assertEqual(enlaces, [None, None],
                         "un traspaso quedó enlazado por un solo lado")

    def test_cuando_va_bien_quedan_los_dos_lados(self):
        from app.routers.transfers import _link_pair

        with cursor() as cur:
            izq, der = self._dos_movimientos(cur)
            ok, _ = _link_pair(cur, izq, der)
        self.assertTrue(ok)
        with cursor() as cur:
            filas = {r["id"]: r["transfer_id"] for r in cur.execute(
                "SELECT id, transfer_id FROM transactions WHERE id IN (?, ?)", (izq, der))}
        self.assertEqual(filas[izq], der)
        self.assertEqual(filas[der], izq)


if __name__ == "__main__":
    unittest.main()
