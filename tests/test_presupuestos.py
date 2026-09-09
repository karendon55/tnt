"""
Tests del cálculo de presupuestos.

Un presupuesto es un límite mensual por categoría. La cuenta parece trivial
—sumar gastos y dividir— pero tiene cuatro trampas que no dan error, solo un
número equivocado:

· los traspasos entre cuentas propias no son gasto;
· los ingresos tampoco, aunque caigan en una categoría con presupuesto;
· un presupuesto de una categoría padre incluye lo de sus hijas;
· y si hay presupuesto en la madre Y en una hija, el total no puede contar
  ese gasto dos veces.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-presu-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "presu.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.budgets import _load_budgets, _totals  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

MES = ("2026-08-01", "2026-08-31")
_n = [0]


def _limpiar(cur):
    for tabla in ("budgets", "transactions", "categories", "accounts"):
        cur.execute(f"DELETE FROM {tabla}")
    cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
    return cur.lastrowid


def _cat(cur, nombre, padre=None):
    cur.execute("INSERT INTO categories(name, kind, parent_id) VALUES (?, 'expense', ?)",
                (nombre, padre))
    return cur.lastrowid


def _presupuesto(cur, cat_id, limite):
    cur.execute("INSERT INTO budgets(category_id, monthly_limit, active) VALUES (?, ?, 1)",
                (cat_id, limite))
    return cur.lastrowid


def _gasto(cur, cuenta, importe, cat=None, fecha="2026-08-10", transfer=None):
    _n[0] += 1
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, hash,"
        " category_id, transfer_id) VALUES (?, ?, ?, 'x', ?, ?, ?)",
        (cuenta, fecha, importe, f"hp{_n[0]}", cat, transfer))
    return cur.lastrowid


class TestLoQueCuentaComoGastado(unittest.TestCase):
    def test_suma_los_gastos_del_mes_de_esa_categoria(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Alimentación")
            _presupuesto(cur, c, 400.0)
            _gasto(cur, cta, -30.0, c)
            _gasto(cur, cta, -70.5, c)
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 100.5)
        self.assertEqual(items[0]["remaining"], 299.5)

    def test_los_traspasos_no_son_gasto(self):
        """Mover dinero de tu cuenta a tu cuenta no gasta nada."""
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Hogar")
            _presupuesto(cur, c, 200.0)
            _gasto(cur, cta, -50.0, c)
            # los dos lados de un traspaso, enlazados entre sí
            otra = _gasto(cur, cta, 500.0, c)
            sale = _gasto(cur, cta, -500.0, c, transfer=otra)
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?",
                        (sale, otra))
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 50.0)

    def test_los_ingresos_no_restan_del_presupuesto(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Ocio")
            _presupuesto(cur, c, 100.0)
            _gasto(cur, cta, -40.0, c)
            _gasto(cur, cta, 25.0, c)      # una devolución
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 40.0,
                         "un ingreso se comió parte del gasto del mes")

    def test_lo_de_otro_mes_no_cuenta(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Transporte")
            _presupuesto(cur, c, 100.0)
            _gasto(cur, cta, -10.0, c, fecha="2026-08-31")
            _gasto(cur, cta, -99.0, c, fecha="2026-09-01")
            _gasto(cur, cta, -99.0, c, fecha="2026-07-31")
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 10.0, "se coló un mes vecino")

    def test_lo_sin_categoria_no_cuenta(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Compras")
            _presupuesto(cur, c, 100.0)
            _gasto(cur, cta, -80.0, None)
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 0)

    def test_el_presupuesto_de_la_madre_incluye_a_las_hijas(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            madre = _cat(cur, "Hogar")
            luz = _cat(cur, "Luz y gas", padre=madre)
            _presupuesto(cur, madre, 300.0)
            _gasto(cur, cta, -60.0, luz)
            _gasto(cur, cta, -40.0, madre)
            items = _load_budgets(cur, *MES)
        self.assertEqual(items[0]["spent"], 100.0)


class TestPorcentajeYEstado(unittest.TestCase):
    def _uno(self, limite, gastado):
        with cursor() as cur:
            cta = _limpiar(cur)
            c = _cat(cur, "Cat")
            _presupuesto(cur, c, limite)
            if gastado:
                _gasto(cur, cta, -gastado, c)
            return _load_budgets(cur, *MES)[0]

    def test_a_medias_ni_avisa_ni_se_pasa(self):
        i = self._uno(200.0, 50.0)
        self.assertEqual(i["pct"], 25.0)
        self.assertFalse(i["warn"])
        self.assertFalse(i["over"])

    def test_cerca_del_limite_avisa(self):
        i = self._uno(100.0, 85.0)
        self.assertTrue(i["warn"])
        self.assertFalse(i["over"])

    def test_justo_en_el_limite_avisa_pero_no_se_ha_pasado(self):
        i = self._uno(100.0, 100.0)
        self.assertEqual(i["pct"], 100.0)
        self.assertTrue(i["warn"])
        self.assertFalse(i["over"])

    def test_pasarse_es_pasarse(self):
        i = self._uno(100.0, 130.0)
        self.assertEqual(i["pct"], 130.0)
        self.assertTrue(i["over"])
        self.assertEqual(i["remaining"], -30.0)

    def test_sin_gastar_nada(self):
        i = self._uno(100.0, 0)
        self.assertEqual(i["pct"], 0)
        self.assertEqual(i["remaining"], 100.0)


class TestTotales(unittest.TestCase):
    def test_suma_limites_y_gastos(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            a, b = _cat(cur, "A"), _cat(cur, "B")
            _presupuesto(cur, a, 100.0)
            _presupuesto(cur, b, 300.0)
            _gasto(cur, cta, -50.0, a)
            _gasto(cur, cta, -150.0, b)
            t = _totals(cur, _load_budgets(cur, *MES), *MES)
        self.assertEqual(t["limit"], 400.0)
        self.assertEqual(t["spent"], 200.0)
        self.assertEqual(t["pct"], 50.0)
        self.assertFalse(t["over"])

    def test_un_gasto_no_se_cuenta_dos_veces(self):
        """Con presupuesto en la madre Y en una hija, el gasto de la hija está
        dentro de los dos. Sumando filas se contaría dos veces y el total diría
        que has gastado el doble de lo que has gastado."""
        with cursor() as cur:
            cta = _limpiar(cur)
            madre = _cat(cur, "Hogar")
            luz = _cat(cur, "Luz y gas", padre=madre)
            _presupuesto(cur, madre, 300.0)
            _presupuesto(cur, luz, 100.0)
            _gasto(cur, cta, -80.0, luz)
            items = _load_budgets(cur, *MES)
            t = _totals(cur, items, *MES)
        # cada presupuesto, por separado, sí ve sus 80 €
        self.assertEqual({i["spent"] for i in items}, {80.0})
        self.assertEqual(t["spent"], 80.0,
                         "el total contó dos veces el mismo movimiento")

    def test_sin_presupuestos_no_divide_por_cero(self):
        with cursor() as cur:
            _limpiar(cur)
            t = _totals(cur, [], *MES)
        self.assertEqual(t["pct"], 0)
        self.assertEqual(t["spent"], 0)


class TestLimiteQueNoTieneSentido(unittest.TestCase):
    """Un límite de 0 o negativo no da error: deja el porcentaje en 0 y la
    barra no avisa nunca. Se rechaza en el borde."""

    def _crear(self, limite):
        with cursor() as cur:
            _limpiar(cur)
            c = _cat(cur, "Cat")
        client.post("/presupuestos/nuevo",
                    data={"category_id": c, "monthly_limit": limite},
                    follow_redirects=False)
        with cursor() as cur:
            return cur.execute("SELECT COUNT(*) AS n FROM budgets").fetchone()["n"]

    def test_no_se_crea_con_limite_cero(self):
        self.assertEqual(self._crear(0), 0)

    def test_no_se_crea_con_limite_negativo(self):
        self.assertEqual(self._crear(-50), 0)

    def test_uno_normal_si_se_crea(self):
        self.assertEqual(self._crear(120.5), 1)

    def test_no_se_edita_a_un_limite_imposible(self):
        with cursor() as cur:
            _limpiar(cur)
            c = _cat(cur, "Cat")
            b = _presupuesto(cur, c, 200.0)
        client.post(f"/presupuestos/{b}/editar", data={"monthly_limit": -1},
                    follow_redirects=False)
        with cursor() as cur:
            limite = cur.execute(
                "SELECT monthly_limit AS l FROM budgets WHERE id = ?", (b,)).fetchone()["l"]
        self.assertEqual(limite, 200.0, "se guardó un límite negativo")


if __name__ == "__main__":
    unittest.main()
