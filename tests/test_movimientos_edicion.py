"""
Tests de crear, editar y borrar un movimiento a mano, y de su nota.

Son las escrituras que el usuario hace sobre un movimiento entero. Lo delicado
es el traspaso: dos movimientos enlazados dejan de ser un traspaso si a uno le
cambias el importe, la fecha o la cuenta, y el enlace tiene que soltarse por
los dos lados. Un lado suelto es dinero que el panel deja de contar.

Datos inventados. La base es temporal, pero `unittest discover` comparte
proceso: cada test limpia al entrar y al salir.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-movimientos-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "movimientos.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class _ConCuentas(unittest.TestCase):
    def setUp(self):
        self._limpiar()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Banco A', 'bank')")
            self.a = cur.lastrowid
            cur.execute("INSERT INTO accounts(name, type) VALUES ('Banco B', 'bank')")
            self.b = cur.lastrowid
            cur.execute("INSERT INTO categories(name, kind) VALUES ('Prueba de movimientos', 'expense')")
            self.cat = cur.lastrowid
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")
            cur.execute("DELETE FROM categories WHERE name = 'Prueba de movimientos'")

    def _movimiento(self, cuenta, importe, descripcion="COMPRA", fecha="2026-05-03", **campos) -> int:
        columnas = {"account_id": cuenta, "date": fecha, "amount": importe, "description": descripcion,
                    "hash": f"prueba-{cuenta}-{fecha}-{importe}-{descripcion}", **campos}
        with cursor() as cur:
            cur.execute(f"INSERT INTO transactions({', '.join(columnas)}) "
                        f"VALUES ({', '.join('?' * len(columnas))})", list(columnas.values()))
            return cur.lastrowid

    def _traspaso(self) -> tuple[int, int]:
        sale = self._movimiento(self.a, -100.0, "TRASPASO A B")
        entra = self._movimiento(self.b, 100.0, "TRASPASO DE A")
        with cursor() as cur:
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (entra, sale))
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (sale, entra))
        return sale, entra

    @staticmethod
    def _filas() -> list[dict]:
        with cursor() as cur:
            return [dict(r) for r in cur.execute("SELECT * FROM transactions ORDER BY id")]

    def _fila(self, tx_id) -> dict | None:
        return next((f for f in self._filas() if f["id"] == tx_id), None)

    def _formulario(self, **cambios) -> dict:
        datos = {"account_id": str(self.a), "date": "2026-05-03", "amount": "-12.50",
                 "description": "Merienda", "memo": "", "category_id": ""}
        return {**datos, **{k: str(v) for k, v in cambios.items()}}


class TestNuevo(_ConCuentas):
    def _crear(self, **cambios):
        return client.post("/movimientos/nuevo", data=self._formulario(**cambios), follow_redirects=False)

    def test_crea_el_movimiento_y_vuelve_a_la_lista(self):
        r = self._crear(description="  Merienda  ", memo="  en el parque ", category_id=self.cat)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/movimientos"))
        (fila,) = self._filas()
        esperado = {"account_id": self.a, "date": "2026-05-03", "amount": -12.5, "description": "Merienda",
                    "memo": "en el parque", "category_id": self.cat, "auto_categorized": 0,
                    "confidence": 1.0, "transfer_id": None, "source_hint": "manual"}
        self.assertEqual({k: fila[k] for k in esperado}, esperado)
        self.assertTrue(fila["hash"].startswith("manual:"), fila["hash"])

    def test_sin_categoria_ni_nota_quedan_vacias(self):
        self._crear()
        (fila,) = self._filas()
        self.assertEqual((fila["category_id"], fila["confidence"], fila["memo"]), (None, None, None))

    def test_una_descripcion_en_blanco_no_queda_vacia(self):
        self._crear(description="   ")
        self.assertEqual(self._filas()[0]["description"], "(manual)")

    def test_dos_iguales_el_mismo_dia_entran_los_dos(self):
        # Dos cafés de 2 € no son un duplicado: la huella lleva el momento.
        self._crear()
        self._crear()
        huellas = [f["hash"] for f in self._filas()]
        self.assertEqual(len(huellas), 2)
        self.assertEqual(len(set(huellas)), 2)


class TestEditar(_ConCuentas):
    def _editar(self, tx_id, **cambios):
        return client.post(f"/movimientos/{tx_id}/editar", data=self._formulario(**cambios),
                           follow_redirects=False)

    def test_cambia_los_campos_y_vuelve_a_la_lista(self):
        tx = self._movimiento(self.a, -12.5, "COMPRA EN TIENDA", balance=250.0, category_id=self.cat,
                              auto_categorized=1, confidence=0.8)
        r = self._editar(tx, account_id=self.b, date="2026-05-04", amount="-13.75", description=" Otra cosa ",
                         memo=" nota ", category_id=self.cat)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/movimientos"))
        fila = self._fila(tx)
        esperado = {"account_id": self.b, "date": "2026-05-04", "amount": -13.75, "description": "Otra cosa",
                    "memo": "nota", "category_id": self.cat,
                    # Con categoría, sigue constando si la puso una regla; el saldo
                    # que traía del banco ya no vale para un movimiento retocado.
                    "auto_categorized": 1, "confidence": 0.8, "balance": None}
        self.assertEqual({k: fila[k] for k in esperado}, esperado)

    def test_quitar_la_categoria_borra_tambien_su_origen(self):
        tx = self._movimiento(self.a, -12.5, category_id=self.cat, auto_categorized=1, confidence=0.8)
        self._editar(tx, category_id="")
        fila = self._fila(tx)
        self.assertEqual((fila["category_id"], fila["auto_categorized"], fila["confidence"]), (None, 0, None))

    def test_cambiar_importe_fecha_o_cuenta_suelta_el_traspaso_por_los_dos_lados(self):
        for campo, valor in (("amount", "-90.00"), ("date", "2026-05-09"), ("account_id", None)):
            with self.subTest(cambia=campo):
                self._limpiar_movimientos()
                sale, entra = self._traspaso()
                igual = {"amount": "-100.00", "description": "TRASPASO A B"}
                self._editar(sale, **{**igual, campo: valor if valor is not None else self.b})
                self.assertEqual((self._fila(sale)["transfer_id"], self._fila(entra)["transfer_id"]),
                                 (None, None))

    def test_cambiar_solo_el_texto_conserva_el_traspaso(self):
        sale, entra = self._traspaso()
        self._editar(sale, amount="-100.00", description="Traspaso a la otra cuenta", memo="ahorro")
        self.assertEqual((self._fila(sale)["transfer_id"], self._fila(entra)["transfer_id"]), (entra, sale))
        self.assertEqual(self._fila(sale)["description"], "Traspaso a la otra cuenta")

    def test_editar_uno_que_no_existe_no_escribe_nada(self):
        otro = self._movimiento(self.a, -5.0)
        antes = self._filas()
        r = self._editar(otro + 1000)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self._filas(), antes)

    @staticmethod
    def _limpiar_movimientos():
        with cursor() as cur:
            cur.execute("DELETE FROM transactions")


class TestBorrar(_ConCuentas):
    def test_quita_el_movimiento_y_vuelve_a_la_lista(self):
        tx = self._movimiento(self.a, -5.0)
        otro = self._movimiento(self.a, -7.0, "OTRA")
        r = client.post(f"/movimientos/{tx}/borrar", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/movimientos"))
        self.assertEqual([f["id"] for f in self._filas()], [otro])

    def test_borrar_un_lado_del_traspaso_deja_el_otro_suelto(self):
        sale, entra = self._traspaso()
        client.post(f"/movimientos/{sale}/borrar", follow_redirects=False)
        self.assertIsNone(self._fila(sale))
        self.assertIsNone(self._fila(entra)["transfer_id"])


class TestNota(_ConCuentas):
    def test_se_guarda_sin_espacios_y_la_celda_la_enseña(self):
        tx = self._movimiento(self.a, -5.0)
        r = client.post(f"/movimientos/{tx}/memo", data={"memo": "  regalo de cumpleaños "})
        self.assertEqual(r.status_code, 200)
        self.assertIn("regalo de cumpleaños", r.text)
        self.assertEqual(self._fila(tx)["memo"], "regalo de cumpleaños")

    def test_vacia_la_borra(self):
        tx = self._movimiento(self.a, -5.0, memo="algo")
        client.post(f"/movimientos/{tx}/memo", data={"memo": "   "})
        self.assertIsNone(self._fila(tx)["memo"])


if __name__ == "__main__":
    unittest.main()
