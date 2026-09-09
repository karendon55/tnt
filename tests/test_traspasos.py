"""
Tests del emparejado de traspasos.

Un traspaso entre cuentas propias son dos movimientos: la salida de una cuenta
y la entrada en la otra. Si no se emparejan, el dinero parece un gasto en una
cuenta y un ingreso en la otra, y todos los totales del año salen mal.

Lo que se prueba aquí:

· `_link_pair` — que acepte lo que es un traspaso y rechace lo que no. Cada
  rechazo por su motivo, porque el mensaje es lo único que ve el usuario.
· `_suggestions` — a quién propone emparejar. Es la parte que más trabajo se
  ahorra el usuario y la que falla en silencio: una sugerencia que no aparece
  no se echa de menos.
· `_unlink_pair` — que deshaga los dos lados, no uno.

La atomicidad de `_link_pair` (que no quede enlazado un solo lado si falla la
segunda escritura) vive en `test_transacciones.py`.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-trasp-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "trasp.db")

from app.db import cursor, init_db  # noqa: E402
from app.routers.transfers import (  # noqa: E402
    _link_pair, _pairs, _suggestions, _unlink_pair,
)

init_db()

_n = [0]


def _cuenta(cur, nombre):
    cur.execute("INSERT INTO accounts(name, type) VALUES (?, 'bank')", (nombre,))
    return cur.lastrowid


def _mov(cur, cuenta, importe, fecha="2026-08-10", desc="movimiento"):
    _n[0] += 1
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, hash)"
        " VALUES (?, ?, ?, ?, ?)", (cuenta, fecha, importe, desc, f"h{_n[0]}"))
    return cur.lastrowid


def _limpiar(cur):
    """Cada test parte de una base sin movimientos: las sugerencias miran
    TODA la base y los restos de otro test se colarían como candidatos."""
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM accounts")


class TestEmparejar(unittest.TestCase):
    def test_empareja_los_dos_lados(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            sale = _mov(cur, a, -250.0)
            entra = _mov(cur, b, 250.0)
            ok, _ = _link_pair(cur, sale, entra)
            self.assertTrue(ok)
            filas = {r["id"]: r["transfer_id"] for r in cur.execute(
                "SELECT id, transfer_id FROM transactions")}
        self.assertEqual(filas[sale], entra)
        self.assertEqual(filas[entra], sale)

    def test_no_se_empareja_consigo_mismo(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A")
            uno = _mov(cur, a, -10.0)
            ok, msg = _link_pair(cur, uno, uno)
        self.assertFalse(ok)
        self.assertIn("consigo mismo", msg)

    def test_no_empareja_si_falta_alguno(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A")
            uno = _mov(cur, a, -10.0)
            ok, msg = _link_pair(cur, uno, 999999)
        self.assertFalse(ok)
        self.assertIn("No se encontraron", msg)

    def test_no_empareja_dos_de_la_misma_cuenta(self):
        """Un traspaso de una cuenta a sí misma no existe."""
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A")
            ok, msg = _link_pair(cur, _mov(cur, a, -10.0), _mov(cur, a, 10.0))
        self.assertFalse(ok)
        self.assertIn("misma cuenta", msg)

    def test_no_empareja_importes_que_no_se_anulan(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            ok, msg = _link_pair(cur, _mov(cur, a, -10.0), _mov(cur, b, 11.0))
        self.assertFalse(ok)
        self.assertIn("no suman 0", msg)

    def test_no_empareja_algo_ya_emparejado(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b, c = _cuenta(cur, "A"), _cuenta(cur, "B"), _cuenta(cur, "C")
            sale, entra = _mov(cur, a, -50.0), _mov(cur, b, 50.0)
            _link_pair(cur, sale, entra)
            otro = _mov(cur, c, 50.0)
            ok, msg = _link_pair(cur, sale, otro)
        self.assertFalse(ok)
        self.assertIn("ya está emparejado", msg)

    def test_los_centimos_cuentan_con_redondeo(self):
        """0,1 + 0,2 no es 0,3 en coma flotante; el redondeo a 2 lo arregla."""
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            ok, _ = _link_pair(cur, _mov(cur, a, -0.3), _mov(cur, b, 0.1 + 0.2))
        self.assertTrue(ok, "un par de importes opuestos se rechazó por coma flotante")


class TestDesemparejar(unittest.TestCase):
    def test_deshace_los_dos_lados(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            sale, entra = _mov(cur, a, -70.0), _mov(cur, b, 70.0)
            _link_pair(cur, sale, entra)
            _unlink_pair(cur, sale)
            filas = {r["id"]: r["transfer_id"] for r in cur.execute(
                "SELECT id, transfer_id FROM transactions")}
        self.assertIsNone(filas[sale])
        self.assertIsNone(filas[entra], "quedó un lado enlazado a un movimiento suelto")

    def test_desemparejar_algo_suelto_no_hace_nada(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A")
            suelto = _mov(cur, a, -5.0)
            _unlink_pair(cur, suelto)      # no debe reventar
            _unlink_pair(cur, 999999)


class TestSugerencias(unittest.TestCase):
    def test_propone_el_par_evidente(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            sale = _mov(cur, a, -300.0, "2026-08-10")
            entra = _mov(cur, b, 300.0, "2026-08-11")
            s = _suggestions(cur)
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["left_id"], s[0]["right_id"]), (sale, entra))

    def test_propone_aunque_la_salida_se_importara_despues(self):
        """El orden de importación no debería decidir qué se sugiere.

        Si el extracto de la cuenta que recibe se importa primero, la entrada
        tiene id menor que la salida. Es la mitad de los casos."""
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            entra = _mov(cur, b, 300.0, "2026-08-11")   # id menor
            sale = _mov(cur, a, -300.0, "2026-08-10")   # id mayor
            s = _suggestions(cur)
        self.assertEqual(len(s), 1, "no se sugirió un par evidente por el orden de los ids")
        self.assertEqual({s[0]["left_id"], s[0]["right_id"]}, {sale, entra})

    def test_el_par_sale_una_sola_vez(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            _mov(cur, a, -120.0, "2026-08-10")
            _mov(cur, b, 120.0, "2026-08-10")
            s = _suggestions(cur)
        self.assertEqual(len(s), 1, "el mismo par se propuso por los dos lados")

    def test_la_salida_va_siempre_a_la_izquierda(self):
        """La plantilla enseña «izquierda → derecha»: de dónde sale y a dónde
        entra. Si se invierte, se lee al revés."""
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            _mov(cur, b, 55.0, "2026-08-11")
            _mov(cur, a, -55.0, "2026-08-10")
            s = _suggestions(cur)
        self.assertLess(s[0]["left_amount"], 0)
        self.assertGreater(s[0]["right_amount"], 0)

    def test_no_propone_nada_de_la_misma_cuenta(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A")
            _mov(cur, a, -80.0)
            _mov(cur, a, 80.0)
            self.assertEqual(_suggestions(cur), [])

    def test_no_propone_si_pasan_mas_de_tres_dias(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            _mov(cur, a, -80.0, "2026-08-01")
            _mov(cur, b, 80.0, "2026-08-05")
            self.assertEqual(_suggestions(cur), [])

    def test_no_propone_lo_que_ya_esta_emparejado(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            sale, entra = _mov(cur, a, -90.0), _mov(cur, b, 90.0)
            _link_pair(cur, sale, entra)
            self.assertEqual(_suggestions(cur), [])


class TestPares(unittest.TestCase):
    def test_un_par_emparejado_sale_una_vez(self):
        with cursor() as cur:
            _limpiar(cur)
            a, b = _cuenta(cur, "A"), _cuenta(cur, "B")
            sale, entra = _mov(cur, a, -40.0), _mov(cur, b, 40.0)
            _link_pair(cur, sale, entra)
            p = _pairs(cur)
        self.assertEqual(len(p), 1)
        self.assertEqual({p[0]["left_id"], p[0]["right_id"]}, {sale, entra})


if __name__ == "__main__":
    unittest.main()
