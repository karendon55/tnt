"""
Tests de la carga del histórico de HomeBank: los traspasos y los saldos.

- Solo se emparejan como traspaso los movimientos marcados como tales: por
  importe a secas, dos Bizum de 15 € el mismo día serían una pareja falsa.
- Los saldos de después (2026) no se mueven ni un céntimo: el saldo inicial
  de cada cuenta retrocede exactamente lo que se movió en el año cargado.
- Si HomeBank no cuadra con el banco a fin de año, la diferencia queda como
  un movimiento visible («Discrepancia en la importación»), no escondida.

Datos inventados, los de base_homebank_historico.py.
"""
import os
import tempfile
import unittest
from datetime import date

from app.db import cursor
from app.importers import homebank_xhb
from app.services import homebank_historico as hh
from app.services.balances import balances_by_account
from tests.base_homebank_historico import XHB, BaseHistorico, D, ope


class TestTraspasos(BaseHistorico):
    def test_se_emparejan_los_marcados(self):
        r = self._cargar()
        ida = self._filas("description = 'Traspaso a B'")[0]
        vuelta = self._filas("description = 'Traspaso de A'")[0]
        self.assertEqual((ida["transfer_id"], vuelta["transfer_id"]), (vuelta["id"], ida["id"]))
        self.assertEqual(r.emparejados, 2 + 1)  # Ahorro, el fondo de 2025 y la corrección de 2026

    def test_el_que_no_tiene_pareja_se_avisa_y_queda_suelto(self):
        r = self._cargar()
        self.assertEqual([(o.fecha, o.importe) for o in r.sin_pareja], [(date(2025, 4, 1), D("-50.00"))])
        self.assertIsNone(self._filas("description = 'Sin pareja'")[0]["transfer_id"])

    def test_el_ajuste_empareja_el_traspaso_al_fondo(self):
        self._cargar()
        banco, fondo = sorted(self._filas("description = 'Comisiones fondo'"), key=lambda x: x["amount"])
        self.assertEqual((banco["transfer_id"], fondo["transfer_id"]), (fondo["id"], banco["id"]))
        self.assertEqual({banco["category_id"], fondo["category_id"]}, {self.cat["traspaso"]})

    def test_la_correccion_de_2026_crea_la_contrapartida_y_empareja(self):
        self._cargar()
        a, b, f = self.tnt
        original = self._filas("id = ?", (self.aportacion_2026,))[0]
        pareja = self._filas("id = ?", (original["transfer_id"],))[0]
        self.assertEqual((pareja["account_id"], pareja["amount"], pareja["date"]), (f, 120.0, "2026-03-24"))
        self.assertEqual(original["category_id"], self.cat["traspaso"])

    def test_una_correccion_que_no_coincide_no_escribe_nada(self):
        mala = hh.Correccion(self.aportacion_2026, date(2026, 3, 24), D("-999.00"), self.tnt[2],
                             self.cat["traspaso"])
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "no coincide"):
                hh.cargar(cur, self.libro, self._plan(correcciones=(mala,)))
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])


class TestTraspasosDeUnaMismaCuenta(BaseHistorico):
    def test_dos_opuestos_de_la_misma_cuenta_no_son_un_traspaso(self):
        extra = (ope(date(2025, 7, 1), "60", 1, category="3", wording="Entra 60")
                 + ope(date(2025, 7, 1), "-60", 1, category="3", wording="Sale 60"))
        fd, ruta = tempfile.mkstemp(suffix=".xhb")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(XHB.replace("</homebank>", extra + "\n</homebank>"))
        self.addCleanup(os.remove, ruta)
        self.libro = homebank_xhb.leer(ruta)
        r = self._cargar()
        for descripcion in ("Entra 60", "Sale 60"):
            with self.subTest(movimiento=descripcion):
                self.assertIsNone(self._filas("description = ?", (descripcion,))[0]["transfer_id"])
        self.assertEqual(sum(1 for o in r.sin_pareja if o.fecha == date(2025, 7, 1)), 2)


class TestSaldos(BaseHistorico):
    FECHAS = ("2025-12-31", "2026-01-02", "2026-01-31", "2026-06-30", "2026-12-31")

    def _saldos(self, cuentas, fechas):
        with cursor() as cur:
            return {f: {c: balances_by_account(cur, f)[c] for c in cuentas} for f in fechas}

    def test_los_saldos_del_banco_desde_el_cierre_del_ejercicio_no_cambian(self):
        bancos = self.tnt[:2]
        antes = self._saldos(bancos, self.FECHAS)
        self._cargar()
        self.assertEqual(self._saldos(bancos, self.FECHAS), antes)

    def test_el_fondo_vale_lo_mismo_desde_su_primera_valoracion_de_2026(self):
        # Antes de ella no tenía ninguna y TNT enseñaba lo aportado; ahora
        # enseña el valor real de diciembre. Eso cambia, y es lo correcto.
        fondo, fechas = self.tnt[2:], self.FECHAS[2:]
        antes = self._saldos(fondo, fechas)
        self._cargar()
        self.assertEqual(self._saldos(fondo, fechas), antes)
        self.assertEqual(self._saldos(fondo, ["2026-01-02"])["2026-01-02"][self.tnt[2]], 51642.18)

    def test_la_discrepancia_queda_a_la_vista(self):
        r = self._cargar()
        a, b, f = self.tnt
        self.assertEqual(r.discrepancias, {a: D("-8.15")})
        ajuste = self._filas("hash LIKE 'homebank:2025:discrepancia:%'")
        self.assertEqual([(x["account_id"], x["date"], x["amount"], x["category_id"], x["memo"]) for x in ajuste],
                         [(a, "2025-12-31", -8.15, self.cat["otros_gastos"], "Discrepancia en la importación")])

    def test_el_saldo_inicial_pasa_a_ser_la_apertura_del_ejercicio(self):
        r = self._cargar()
        a, b, f = self.tnt
        with cursor() as cur:
            iniciales = dict(cur.execute("SELECT id, initial_balance FROM accounts"))
        self.assertEqual(round(iniciales[a], 2), float(self.libro.saldo(1, date(2024, 12, 31))))
        self.assertEqual(round(iniciales[b], 2), float(self.libro.saldo(2, date(2024, 12, 31))))
        self.assertEqual(iniciales[f], 50000.0)  # el del fondo, fijado en el plan
        self.assertEqual(r.saldos_iniciales[a], (D("2281.85"), D("995.00")))

    def test_las_valoraciones_del_fondo(self):
        self._cargar()
        with cursor() as cur:
            fechas = [r[0] for r in cur.execute(
                "SELECT date FROM account_valuations WHERE account_id = ? ORDER BY date", (self.tnt[2],))]
        self.assertEqual(fechas, ["2025-12-31", "2026-01-31"])


if __name__ == "__main__":
    unittest.main()
