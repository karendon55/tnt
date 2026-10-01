"""
Tests de las reglas de transferencia externa, y en concreto del importe exacto.

Una regla refleja un movimiento como entrada en otra cuenta y enlaza los dos
como traspaso, para que no cuenten como gasto ni como ingreso. Casaba solo por
descripción, y eso no basta con dos depósitos de EuroCaja: los dos generan
«DEPOSITO A PLAZO» y «CANCELACION PLAZO», sin número de contrato. Lo único que
los distingue es el importe (60.000 € uno, 150.000 € el otro), así que una
regla puede llevar ahora un importe exacto.

Tres trampas que estos tests fijan:

· el orden: si casan una regla con importe y una genérica, gana la del
  importe. Antes las reglas se aplicaban sin ORDER BY;
· el borrado: quitar una regla con importe no puede llevarse los espejos de
  otros importes. Si lo hiciera, la cancelación de 100.000 € de agosto
  perdería su espejo y volvería a contar como ingreso;
· el duplicado: una regla repetida se ignoraba en silencio.

La base es temporal y propia, pero `unittest discover` comparte proceso con
otros ficheros: por eso cada test limpia al entrar y al salir.
"""
import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-reglas-traspaso-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "reglas.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.external_transfers import apply_rules  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")

ANUAL, NUEVE_MESES = 150000.0, 60000.0


class _Base(unittest.TestCase):
    def setUp(self):
        self._vaciar()
        with cursor() as cur:
            self.eurocaja = self._cuenta(cur, "EuroCaja Rural")
            self.anual = self._cuenta(cur, "Depósito anual")
            self.nueve = self._cuenta(cur, "Depósito 9M")
        self._n = 0

    def tearDown(self):
        self._vaciar()

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM external_transfer_rules")
            cur.execute("DELETE FROM transactions")
            cur.execute("DELETE FROM accounts")

    @staticmethod
    def _cuenta(cur, nombre):
        cur.execute("INSERT INTO accounts(name, type) VALUES (?, 'bank')", (nombre,))
        return cur.lastrowid

    def _mov(self, fecha, importe, desc):
        self._n += 1
        with cursor() as cur:
            cur.execute(
                "INSERT INTO transactions(account_id, date, amount, description, hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.eurocaja, fecha, importe, desc, f"mov-{self._n}"),
            )
            return cur.lastrowid

    def _regla(self, patron, destino, importe=None):
        with cursor() as cur:
            cur.execute(
                "INSERT INTO external_transfer_rules"
                "(pattern, source_account_id, target_account_id, amount, active) "
                "VALUES (?, ?, ?, ?, 1)",
                (patron, self.eurocaja, destino, importe),
            )
            return cur.lastrowid

    def _aplicar(self):
        with cursor() as cur:
            return apply_rules(cur)

    @staticmethod
    def _espejo_de(mov_id):
        """Cuenta en la que quedó el espejo de un movimiento, o None."""
        with cursor() as cur:
            r = cur.execute(
                "SELECT m.account_id FROM transactions t "
                "JOIN transactions m ON m.id = t.transfer_id WHERE t.id = ?",
                (mov_id,),
            ).fetchone()
            return r["account_id"] if r else None


class TestImporteExacto(_Base):
    def test_regla_con_importe_solo_casa_ese_importe(self):
        de_60 = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        de_150 = self._mov("2026-08-20", -ANUAL, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self._aplicar()
        self.assertEqual(self._espejo_de(de_60), self.nueve)
        self.assertIsNone(self._espejo_de(de_150))

    def test_cada_deposito_va_a_su_cuenta(self):
        # El caso real: dos depósitos con la misma descripción.
        de_60 = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        de_150 = self._mov("2026-08-20", -ANUAL, "DEPOSITO A PLAZO")
        cancel_60 = self._mov("2027-02-14", NUEVE_MESES, "CANCELACION PLAZO")
        for patron in ("deposito a plazo", "cancelacion plazo"):
            self._regla(patron, self.anual, ANUAL)
            self._regla(patron, self.nueve, NUEVE_MESES)
        self._aplicar()
        self.assertEqual(self._espejo_de(de_60), self.nueve)
        self.assertEqual(self._espejo_de(de_150), self.anual)
        # La que preocupaba: el vencimiento del de 9 meses, en febrero.
        self.assertEqual(self._espejo_de(cancel_60), self.nueve)

    def test_compara_en_valor_absoluto(self):
        # La regla guarda 60.000; la cancelación llega en positivo y la
        # apertura en negativo. Las dos son de ese depósito.
        apertura = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        cancelacion = self._mov("2027-02-14", NUEVE_MESES, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self._aplicar()
        self.assertEqual(self._espejo_de(apertura), self.nueve)
        self.assertEqual(self._espejo_de(cancelacion), self.nueve)

    def test_compara_a_centimos(self):
        # Un REAL de SQLite puede traer ruido en el último decimal.
        mov = self._mov("2026-05-14", -60000.004, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self._aplicar()
        self.assertEqual(self._espejo_de(mov), self.nueve)

    def test_importe_desconocido_no_casa_con_ninguna(self):
        # Un depósito nuevo de otro importe no se reparte a ciegas: se queda
        # sin espejo y sale en los KPIs, donde se ve.
        nuevo = self._mov("2027-03-01", -75000.0, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.anual, ANUAL)
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self.assertEqual(self._aplicar(), 0)
        self.assertIsNone(self._espejo_de(nuevo))


class TestOrdenDeAplicacion(_Base):
    def test_la_regla_con_importe_gana_a_la_generica(self):
        de_60 = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        de_150 = self._mov("2026-08-20", -ANUAL, "DEPOSITO A PLAZO")
        # La genérica se crea PRIMERO: sin orden explícito ganaría ella.
        self._regla("deposito a plazo", self.anual, None)
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self._aplicar()
        self.assertEqual(self._espejo_de(de_60), self.nueve)
        self.assertEqual(self._espejo_de(de_150), self.anual)

    def test_una_regla_sin_importe_sigue_casando_con_todo(self):
        a = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        b = self._mov("2026-08-20", -ANUAL, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.anual, None)
        self.assertEqual(self._aplicar(), 2)
        self.assertEqual(self._espejo_de(a), self.anual)
        self.assertEqual(self._espejo_de(b), self.anual)

    def test_aplicar_dos_veces_no_duplica_espejos(self):
        self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self.assertEqual(self._aplicar(), 1)
        self.assertEqual(self._aplicar(), 0)


class TestBorrado(_Base):
    def test_borrar_regla_con_importe_respeta_espejos_de_otros_importes(self):
        # Agosto: la cancelación de un depósito viejo de 100.000 € quedó
        # reflejada en la cuenta del anual por la regla genérica de entonces.
        cancel_100 = self._mov("2026-08-20", 100000.0, "CANCELACION PLAZO")
        generica = self._regla("cancelacion plazo", self.anual, None)
        self._aplicar()
        self.assertEqual(self._espejo_de(cancel_100), self.anual)
        # La genérica pasa a ser la del depósito anual, de 150.000 €.
        with cursor() as cur:
            cur.execute("UPDATE external_transfer_rules SET amount = ? WHERE id = ?",
                        (ANUAL, generica))
        r = client.post(f"/reglas-transferencias/{generica}/borrar",
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        # Los 100.000 € tienen que seguir siendo traspaso, no ingreso.
        self.assertEqual(self._espejo_de(cancel_100), self.anual)

    def test_borrar_regla_quita_sus_propios_espejos(self):
        mov = self._mov("2026-05-14", -NUEVE_MESES, "DEPOSITO A PLAZO")
        regla = self._regla("deposito a plazo", self.nueve, NUEVE_MESES)
        self._aplicar()
        client.post(f"/reglas-transferencias/{regla}/borrar", follow_redirects=False)
        self.assertIsNone(self._espejo_de(mov))
        with cursor() as cur:
            vivos = cur.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE account_id = ?",
                (self.nueve,),
            ).fetchone()["n"]
        self.assertEqual(vivos, 0)


class TestFormulario(_Base):
    def _crear(self, **campos):
        datos = {"pattern": "deposito a plazo", "source_account_id": str(self.eurocaja),
                 "target_account_id": str(self.nueve), "note": "", "amount": ""}
        datos.update(campos)
        r = client.post("/reglas-transferencias/nueva", data=datos,
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        destino = urlsplit(r.headers["location"])
        return destino.path, parse_qs(destino.query)

    @staticmethod
    def _reglas():
        with cursor() as cur:
            return [dict(r) for r in cur.execute(
                "SELECT pattern, target_account_id, amount FROM external_transfer_rules")]

    def test_crea_regla_con_importe_y_vuelve_a_reglas(self):
        ruta, qs = self._crear(amount="60000")
        self.assertEqual(ruta, "/reglas")
        self.assertIn("msg", qs)
        self.assertEqual(self._reglas()[0]["amount"], 60000.0)

    def test_acepta_coma_decimal(self):
        self._crear(amount="60000,50")
        self.assertEqual(self._reglas()[0]["amount"], 60000.5)

    def test_sin_importe_la_regla_es_generica(self):
        self._crear(amount="")
        self.assertIsNone(self._reglas()[0]["amount"])

    def test_rechaza_importe_cero_negativo_o_basura(self):
        for malo in ("0", "-5", "abc", "nan", "inf"):
            with self.subTest(importe=malo):
                ruta, qs = self._crear(amount=malo)
                self.assertEqual(ruta, "/reglas")
                self.assertIn("err", qs)
                self.assertEqual(self._reglas(), [])

    def test_rechaza_origen_igual_a_destino(self):
        ruta, qs = self._crear(target_account_id=str(self.eurocaja))
        self.assertIn("err", qs)
        self.assertEqual(self._reglas(), [])

    def test_un_duplicado_avisa_en_vez_de_ignorarse(self):
        self._crear(amount="60000")
        ruta, qs = self._crear(amount="60000")
        self.assertIn("err", qs)
        self.assertEqual(len(self._reglas()), 1)

    def test_la_pagina_de_reglas_muestra_el_importe_y_el_aviso(self):
        self._crear(amount="60000")
        html = client.get("/reglas?msg=Regla+creada").text
        self.assertIn("60.000,00", html)
        self.assertIn("Regla creada", html)


if __name__ == "__main__":
    unittest.main()
