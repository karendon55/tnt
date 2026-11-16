"""
Tests del saldo por cuenta calculado en bloque.

`/cuentas` y el panel preguntaban el saldo cuenta por cuenta: con nueve, 39
consultas por página; con cien, 403. `balances_by_account` los saca todos de
una vez.

Cambiar cómo se calcula un saldo es lo más delicado que se puede tocar aquí,
así que lo que se prueba no es «da un número», es «da EXACTAMENTE el mismo
número que antes», caso por caso y también en conjunto. Las cuentas de
inversión son el caso raro: mandan por su última valoración declarada, y solo
si no hay ninguna cuentan lo aportado.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-saldos-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "saldos.db")

from app.db import cursor, init_db  # noqa: E402
from app.services.balances import (  # noqa: E402
    account_balance, balances_by_account, total_balance,
)

init_db()
_n = [0]


def _limpiar(cur):
    for tabla in ("account_valuations", "transactions", "accounts"):
        cur.execute(f"DELETE FROM {tabla}")


def _cuenta(cur, nombre, tipo="bank", inicial=0.0, archivada=0):
    cur.execute(
        "INSERT INTO accounts(name, type, initial_balance, currency, archived)"
        " VALUES (?, ?, ?, 'EUR', ?)", (nombre, tipo, inicial, archivada))
    return cur.lastrowid


def _mov(cur, cuenta, importe, fecha="2026-08-10"):
    _n[0] += 1
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, hash)"
        " VALUES (?, ?, ?, 'x', ?)", (cuenta, fecha, importe, f"hs{_n[0]}"))


def _valoracion(cur, cuenta, valor, fecha):
    cur.execute(
        "INSERT INTO account_valuations(account_id, date, value) VALUES (?, ?, ?)",
        (cuenta, fecha, valor))


class TestSaldoEnBloque(unittest.TestCase):
    def test_saldo_inicial_mas_movimientos(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "Corriente", inicial=100.0)
            _mov(cur, a, -30.0)
            _mov(cur, a, 12.5)
            self.assertEqual(balances_by_account(cur)[a], 82.5)

    def test_una_cuenta_sin_movimientos_vale_su_saldo_inicial(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "Recién abierta", inicial=250.0)
            self.assertEqual(balances_by_account(cur)[a], 250.0)

    def test_las_archivadas_tambien_salen(self):
        """Quien llama decide si las enseña; la función no se las come."""
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "Vieja", inicial=40.0, archivada=1)
            self.assertIn(a, balances_by_account(cur))

    def test_la_inversion_manda_por_su_ultima_valoracion(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "Fondo", tipo="investment", inicial=0.0)
            _mov(cur, a, 1000.0)                      # aportado
            _valoracion(cur, a, 900.0, "2026-06-30")
            _valoracion(cur, a, 1180.0, "2026-08-31")  # la buena
            self.assertEqual(balances_by_account(cur)[a], 1180.0)

    def test_una_inversion_sin_valorar_vale_lo_aportado(self):
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "Fondo nuevo", tipo="investment", inicial=0.0)
            _mov(cur, a, 500.0)
            self.assertEqual(balances_by_account(cur)[a], 500.0)

    def test_no_puede_haber_dos_valoraciones_el_mismo_dia(self):
        """El desempate por id no llega a usarse nunca: lo impide el esquema.

        Se fija aquí porque de eso depende que una sola valoración por fecha
        sea suficiente para saber cuál es la última."""
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            with cursor() as cur:
                _limpiar(cur)
                a = _cuenta(cur, "Fondo", tipo="investment")
                _valoracion(cur, a, 100.0, "2026-08-31")
                _valoracion(cur, a, 200.0, "2026-08-31")


class TestDaLoMismoQueUnaAUna(unittest.TestCase):
    """La prueba que importa: el cálculo en bloque y el de siempre no pueden
    discrepar en ninguna cuenta."""

    def test_coinciden_cuenta_por_cuenta(self):
        with cursor() as cur:
            _limpiar(cur)
            corriente = _cuenta(cur, "Corriente", inicial=1234.56)
            for imp in (-12.34, 500.0, -0.99, 87.65):
                _mov(cur, corriente, imp)
            vacia = _cuenta(cur, "Vacía", inicial=0.0)
            archivada = _cuenta(cur, "Archivada", inicial=15.0, archivada=1)
            _mov(cur, archivada, -5.0)
            fondo = _cuenta(cur, "Fondo valorado", tipo="investment")
            _mov(cur, fondo, 2000.0)
            _valoracion(cur, fondo, 2145.30, "2026-08-31")
            fondo2 = _cuenta(cur, "Fondo sin valorar", tipo="investment")
            _mov(cur, fondo2, 300.0)

            bloque = balances_by_account(cur)
            for cta in (corriente, vacia, archivada, fondo, fondo2):
                with self.subTest(cuenta=cta):
                    self.assertEqual(bloque[cta], account_balance(cur, cta))

    def test_el_patrimonio_sigue_saliendo_igual(self):
        """total_balance suma solo las activas, y las de inversión por su
        valoración. Se comprueba contra la suma hecha a mano."""
        with cursor() as cur:
            _limpiar(cur)
            a = _cuenta(cur, "A", inicial=100.0)
            _mov(cur, a, -25.0)
            b = _cuenta(cur, "B", tipo="investment")
            _valoracion(cur, b, 500.0, "2026-08-31")
            _cuenta(cur, "Archivada", inicial=9999.0, archivada=1)
            self.assertEqual(total_balance(cur), 575.0)


if __name__ == "__main__":
    unittest.main()
