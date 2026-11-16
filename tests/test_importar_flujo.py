"""
Tests de la importación de principio a fin: vista previa, confirmar, el
historial de lotes y deshacer uno.

Es el camino por el que entra casi todo el dinero que TNT conoce. Lo que tiene
que cumplir:

- La vista previa no escribe nada: hasta confirmar, la base no cambia.
- Confirmar mete cada fichero entero o no lo mete: uno que falle a medias no
  deja sus movimientos dentro ni tira los de los demás.
- El mismo fichero dos veces no duplica, y deshacer un lote se lleva sus
  movimientos y ninguno más.

Los lectores de cada banco y `ingest` tienen sus propios tests; aquí se prueba
lo que hay alrededor. Datos inventados. La base es temporal, pero `unittest
discover` comparte proceso: cada test limpia al entrar y al salir.
"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="tnt-importar-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "importar.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import import_batches  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


def _extracto(iban="ES00 1111 2222 3333 4444 5555", concepto="PRUEBA") -> bytes:
    """Un CSV como el de la banca online de EuroCaja Rural, con dos movimientos."""
    return ("Cuentas > Consultar > Movimientos;\r\n"
            "Movimientos;\r\n"
            "\r\n"
            f"Cuenta;{iban} - CUENTA DE {concepto};\r\n"
            "Fecha desde;01-05-2026;\r\n"
            "Fecha hasta;31-05-2026;\r\n"
            "\r\n"
            "Fecha de ejecución;Fecha valor;Descripción;Importe;Saldo\r\n"
            f"18-05-2026 06:00;18-05-2026;RECIBO DE {concepto};-25,50   €;974,50   €;\r\n"
            f"14-05-2026 08:58;14-05-2026;INGRESO DE {concepto};1.000,00   €;1.000,00   €;\r\n"
            ).encode("utf-8-sig")


HOMEBANK = ("date;payment;info;payee;memo;amount;category;tags\n"
            "02/03/2025;;;;Compra de antes;-8,40;Comida;\n"
            "05/03/2025;;;;Intereses de antes;3,10;Intereses;\n").encode("utf-8")


def _fichero(nombre: str, contenido: bytes):
    return ("files", (nombre, contenido, "text/csv"))


def _token(html: str) -> str:
    return re.search(r'name="token" value="([0-9a-f]{32})"', html).group(1)


class _Limpio(unittest.TestCase):
    TABLAS = ("transactions", "accounts", "import_batches", "category_rules")

    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        self.addCleanup(self._vaciar)

    def _vaciar(self):
        with cursor() as cur:
            for tabla in self.TABLAS:
                cur.execute(f"DELETE FROM {tabla}")
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    @staticmethod
    def _filas(tabla: str, orden: str = "id") -> list[dict]:
        with cursor() as cur:
            return [dict(r) for r in cur.execute(f"SELECT * FROM {tabla} ORDER BY {orden}")]

    def _cuantas(self) -> dict:
        return {tabla: len(self._filas(tabla)) for tabla in ("transactions", "accounts", "import_batches")}

    @staticmethod
    def _previsualizar(*ficheros):
        return client.post("/importar", files=[_fichero(n, c) for n, c in ficheros])

    def _importar(self, *ficheros):
        r = client.post("/importar/confirmar", data={"token": _token(self._previsualizar(*ficheros).text)})
        self.assertEqual(r.status_code, 200)
        return r


class TestVistaPrevia(_Limpio):
    def test_dice_lo_que_entraria_y_no_escribe_nada(self):
        r = self._previsualizar(("mayo.csv", _extracto()))
        self.assertEqual(r.status_code, 200)
        self.assertIn("mayo.csv", r.text)
        self.assertIn("Confirmar e insertar 2 movimientos", r.text)
        self.assertIn("RECIBO DE PRUEBA", r.text)
        self.assertEqual(self._cuantas(), {"transactions": 0, "accounts": 0, "import_batches": 0})

    def test_lo_que_ya_esta_sale_como_duplicado_y_sin_boton_de_confirmar(self):
        self._importar(("mayo.csv", _extracto()))
        r = self._previsualizar(("mayo.csv", _extracto()))
        self.assertIn("0 nuevos", r.text)
        self.assertIn("2 duplicados", r.text)
        self.assertNotIn('name="token"', r.text)

    def test_un_fichero_ilegible_se_avisa_y_no_impide_ver_los_demas(self):
        r = self._previsualizar(("notas.csv", b"esto;no;es\nun;extracto;\n"), ("apuntes.txt", b"hola"),
                                ("mayo.csv", _extracto()))
        self.assertIn("notas.csv", r.text)
        self.assertIn("Formato CSV no reconocido", r.text)
        self.assertIn("Tipo de archivo .txt no soportado", r.text)
        self.assertIn("Confirmar e insertar 2 movimientos", r.text)

    def test_si_no_se_lee_ninguno_no_hay_nada_que_confirmar(self):
        r = self._previsualizar(("notas.csv", b"esto;no;es\nun;extracto;\n"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('name="token"', r.text)


class TestConfirmar(_Limpio):
    def test_inserta_los_movimientos_en_su_cuenta_y_apunta_el_lote(self):
        r = self._importar(("mayo.csv", _extracto()))
        self.assertIn("Importación completada", r.text)
        (cuenta,) = self._filas("accounts")
        self.assertEqual((cuenta["iban"], cuenta["bank"]), ("ES0011112222333344445555", "EuroCaja Rural"))
        (lote,) = self._filas("import_batches")
        self.assertEqual((lote["inserted"], lote["duplicates"]), (2, 0))
        self.assertEqual(json.loads(lote["files"]), [{
            "filename": "mayo.csv", "bank": "EuroCaja Rural", "account": cuenta["name"],
            "inserted": 2, "duplicates": 0}])
        movimientos = [(m["date"], m["amount"], m["description"], m["account_id"], m["import_batch_id"])
                       for m in self._filas("transactions", "date")]
        self.assertEqual(movimientos, [
            ("2026-05-14", 1000.0, "INGRESO DE PRUEBA", cuenta["id"], lote["id"]),
            ("2026-05-18", -25.5, "RECIBO DE PRUEBA", cuenta["id"], lote["id"])])

    def test_el_mismo_fichero_confirmado_dos_veces_no_duplica_ni_deja_un_lote_vacio(self):
        # Dos pestañas con la misma vista previa: la segunda ya no tiene nada nuevo.
        segunda = _token(self._previsualizar(("mayo.csv", _extracto())).text)
        self._importar(("mayo.csv", _extracto()))
        r = client.post("/importar/confirmar", data={"token": segunda})
        self.assertIn("Importación sin novedades", r.text)
        self.assertEqual(self._cuantas(), {"transactions": 2, "accounts": 1, "import_batches": 1})

    def test_un_token_vale_una_sola_vez_y_uno_desconocido_vuelve_al_formulario(self):
        token = _token(self._previsualizar(("mayo.csv", _extracto())).text)
        client.post("/importar/confirmar", data={"token": token})
        for caso in (token, "0" * 32):
            with self.subTest(token=caso):
                r = client.post("/importar/confirmar", data={"token": caso}, follow_redirects=False)
                self.assertEqual((r.status_code, r.headers["location"]), (303, "/importar"))
        self.assertEqual(self._cuantas()["transactions"], 2)

    def test_si_un_fichero_falla_a_medias_no_deja_nada_suyo_y_los_demas_entran(self):
        de_verdad = import_batches.ingest

        def falla_al_final(cur, extract, batch_id=None):
            resultado = de_verdad(cur, extract, batch_id=batch_id)
            if "ROTO" in extract.account_name:
                raise RuntimeError("se ha roto a mitad")      # con sus filas ya escritas
            return resultado

        token = _token(self._previsualizar(
            ("bueno.csv", _extracto()),
            ("roto.csv", _extracto("ES00 9999 8888 7777 6666 5555", "ROTO"))).text)
        with mock.patch.object(import_batches, "ingest", falla_al_final):
            r = client.post("/importar/confirmar", data={"token": token})
        self.assertIn("roto.csv", r.text)
        self.assertIn("se ha roto a mitad", r.text)
        self.assertEqual(sorted(m["description"] for m in self._filas("transactions")),
                         ["INGRESO DE PRUEBA", "RECIBO DE PRUEBA"])
        self.assertEqual([c["iban"] for c in self._filas("accounts")], ["ES0011112222333344445555"])
        (lote,) = self._filas("import_batches")
        self.assertEqual((lote["inserted"], [f["filename"] for f in json.loads(lote["files"])]), (2, ["bueno.csv"]))

    def test_lo_que_categoriza_una_regla_tuya_al_entrar_cuenta_como_por_reglas(self):
        with cursor() as cur:
            cur.execute("INSERT INTO categories(name, kind) VALUES ('Categoría de prueba', 'expense')")
            categoria = cur.lastrowid
            cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                        "VALUES ('PRUEBA', ?, 100, 'manual', 0)", (categoria,))
        r = self._importar(("mayo.csv", _extracto()))
        self.assertEqual({m["category_id"] for m in self._filas("transactions")}, {categoria})
        self.assertIn("0 por banco · 2 por reglas", r.text)


class TestLotes(_Limpio):
    def test_el_historial_enseña_el_lote_con_su_fichero(self):
        self._importar(("mayo.csv", _extracto()))
        (lote,) = self._filas("import_batches")
        r = client.get("/importar/lotes")
        self.assertEqual(r.status_code, 200)
        self.assertIn(f"#{lote['id']}", r.text)
        self.assertIn("mayo.csv", r.text)

    def test_deshacer_se_lleva_los_movimientos_del_lote_y_ninguno_mas(self):
        self._importar(("mayo.csv", _extracto()))
        (lote,) = self._filas("import_batches")
        (cuenta,) = self._filas("accounts")
        with cursor() as cur:
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, hash) "
                        "VALUES (?, '2026-05-20', -3.0, 'A MANO', 'manual:prueba')", (cuenta["id"],))
        r = client.post(f"/importar/lotes/{lote['id']}/borrar", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"],
                         f"/importar/lotes?msg=Lote+%23{lote['id']}+revertido+(2+movimientos+borrados)")
        self.assertEqual([m["description"] for m in self._filas("transactions")], ["A MANO"])
        self.assertEqual(self._filas("import_batches"), [])


class TestHomeBank(_Limpio):
    def setUp(self):
        super().setUp()
        with cursor() as cur:
            cur.execute("INSERT INTO accounts(name, bank, type) VALUES ('Cuenta de antes', 'Banco', 'bank')")
            self.cuenta = cur.lastrowid

    def _previsualizar_csv(self, contenido: bytes, cuenta: int | None = None):
        return client.post("/importar/homebank", data={"account_id": str(cuenta or self.cuenta)},
                           files={"file": ("antes.csv", contenido, "text/csv")})

    def test_entra_en_la_cuenta_elegida_con_la_categoria_de_homebank_como_pista(self):
        r = self._previsualizar_csv(HOMEBANK)
        self.assertIn("Confirmar e insertar 2 movimientos", r.text)
        self.assertEqual(self._cuantas()["transactions"], 0)
        client.post("/importar/confirmar", data={"token": _token(r.text)})
        movimientos = [(m["date"], m["amount"], m["description"], m["account_id"], m["source_hint"])
                       for m in self._filas("transactions", "date")]
        self.assertEqual(movimientos, [("2025-03-02", -8.4, "Compra de antes", self.cuenta, "Comida"),
                                       ("2025-03-05", 3.1, "Intereses de antes", self.cuenta, "Intereses")])
        self.assertEqual(len(self._filas("accounts")), 1)

    def test_una_linea_mala_se_avisa_y_las_buenas_se_ven(self):
        r = self._previsualizar_csv(HOMEBANK + "99/99/2025;;;;Fecha imposible;-1,00;;\n".encode())
        self.assertIn("línea 4", r.text)
        self.assertIn("Confirmar e insertar 2 movimientos", r.text)

    def test_sin_cuenta_destino_sin_fichero_o_sin_cabecera_no_hay_nada_que_confirmar(self):
        casos = ((HOMEBANK, self.cuenta + 1000, "Cuenta destino no encontrada."),
                 (b"", self.cuenta, "El fichero está vacío."),
                 (b"esto;no;es\nde;homebank;\n", self.cuenta, "no tiene la cabecera de un CSV de HomeBank"))
        for contenido, cuenta, aviso in casos:
            with self.subTest(aviso=aviso):
                r = self._previsualizar_csv(contenido, cuenta)
                self.assertEqual(r.status_code, 200)
                self.assertIn(aviso, r.text)
                self.assertNotIn('name="token"', r.text)


if __name__ == "__main__":
    unittest.main()
