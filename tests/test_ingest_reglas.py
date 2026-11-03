"""
Tests de qué categoría recibe un movimiento al importarse.

ING trae su propia categoría en el extracto, y hasta ahora mandaba siempre: las
reglas solo actuaban sobre lo que llegaba sin categoría. Así, el alquiler que
ING manda como «Otros ingresos (otros)» había que pasarlo a mano cada mes, y
reglas que el usuario creó a propósito no se aplicaban nunca a lo que venía de
ING. Decidido por el usuario:

- Una regla manual que casa gana a la categoría del banco.
- Las aprendidas no: sobre ellas sigue mandando la del banco.
- Sin regla manual, la del banco, como siempre.
- Solo cuenta para lo que entra: reimportar no recategoriza lo que ya estaba.

Datos inventados.
"""
import os
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp(prefix="tnt-ingest-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "ingest.db")

from app.db import cursor, init_db  # noqa: E402
from app.importers.common import ParsedExtract, ParsedTransaction  # noqa: E402
from app.services.categorizer import resolve_category  # noqa: E402
from app.services.ingest import ingest  # noqa: E402

init_db()
IBAN = "ES0000000000000000009999"
BANCO_INGRESO = "Otros ingresos|Otros ingresos (otros)"
BANCO_GASTO = "Compras|Compras (otros)"
ALQUILER = "Traspaso interno recibido Alquiler octubre 26"


class TestCategoriaAlImportar(unittest.TestCase):
    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
            self.alquiler = resolve_category(cur, "Alquiler de prueba", default_kind="income")
            self.super = resolve_category(cur, "Alimentación|Supermercados y alimentación")
            self.banco_ingreso = resolve_category(cur, BANCO_INGRESO, default_kind="income")
            self.banco_gasto = resolve_category(cur, BANCO_GASTO)
            for patron, categoria, fuente in (("RECIBIDO ALQUILER", self.alquiler, "manual"),
                                              ("FRUTAS", self.super, "learned")):
                cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                            "VALUES (?, ?, 150, ?, 5)", (patron, categoria, fuente))

    def tearDown(self):
        with cursor() as cur:
            cur.execute("DELETE FROM accounts WHERE iban = ?", (IBAN,))  # sus movimientos, en cascada
            cur.execute("DELETE FROM category_rules WHERE pattern IN ('RECIBIDO ALQUILER', 'FRUTAS')")
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def _importar(self, *movimientos):
        extracto = ParsedExtract("ING", IBAN, "Cuenta de prueba", "EUR", [
            ParsedTransaction(date(2026, 10, dia), None, importe, texto, source_hint=banco)
            for dia, importe, texto, banco in movimientos])
        with cursor() as cur:
            resultado = ingest(cur, extracto)
            filas = {f[0]: (f[1], f[2]) for f in cur.execute(
                "SELECT t.description, t.category_id, t.auto_categorized FROM transactions t "
                "JOIN accounts a ON a.id = t.account_id WHERE a.iban = ?", (IBAN,))}
        return resultado, filas

    def test_una_regla_manual_gana_a_la_categoria_del_banco(self):
        r, filas = self._importar((1, 950.0, ALQUILER, BANCO_INGRESO))
        self.assertEqual(filas[ALQUILER], (self.alquiler, 1))
        self.assertEqual((r.categorized_from_hint, r.categorized_from_rule), (0, 1))

    def test_una_aprendida_no_gana_a_la_del_banco(self):
        r, filas = self._importar((2, -12.0, "FRUTAS PEPA", BANCO_GASTO))
        self.assertEqual(filas["FRUTAS PEPA"], (self.banco_gasto, 1))
        self.assertEqual((r.categorized_from_hint, r.categorized_from_rule), (1, 0))

    def test_sin_regla_manual_manda_el_banco(self):
        r, filas = self._importar((3, 20.0, "Abono de otra cosa", BANCO_INGRESO))
        self.assertEqual(filas["Abono de otra cosa"], (self.banco_ingreso, 1))

    def test_sin_categoria_del_banco_tambien_la_pone_la_regla(self):
        _, filas = self._importar((4, 950.0, ALQUILER, None))
        self.assertEqual(filas[ALQUILER], (self.alquiler, 1))

    def test_reimportar_no_recategoriza_lo_que_ya_estaba(self):
        with cursor() as cur:
            cur.execute("DELETE FROM category_rules WHERE pattern = 'RECIBIDO ALQUILER'")
        self._importar((1, 950.0, ALQUILER, BANCO_INGRESO))
        with cursor() as cur:  # la regla llega después
            cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                        "VALUES ('RECIBIDO ALQUILER', ?, 150, 'manual', 5)", (self.alquiler,))
        r, filas = self._importar((1, 950.0, ALQUILER, BANCO_INGRESO))
        self.assertEqual(r.duplicates, 1)
        self.assertEqual(filas[ALQUILER], (self.banco_ingreso, 1))


if __name__ == "__main__":
    unittest.main()
