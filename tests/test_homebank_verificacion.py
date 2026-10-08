"""
Tests del comparador de dos bases de TNT (antes y después de cargar historia).

Es la prueba de que el histórico no descuadra lo que ya había: para cada mes
de un periodo compara los saldos de cada cuenta al cierre, el patrimonio y
los ingresos y gastos del mes, y dice exactamente qué cambió. También avisa
de categorías nuevas o perdidas, y de qué reglas aprendidas cambiarían en la
próxima importación por culpa de lo cargado.

Datos inventados. Dos bases temporales: la primera la crea init_db y la
segunda es su copia.
"""
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from datetime import date

_TMP = tempfile.mkdtemp(prefix="tnt-verificacion-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "antes.db")

# La base que usa cursor(): en `unittest discover` la fija el primer fichero que
# importa la configuración, así que releer TNT_DB daría otra.
from app.config import DB_PATH  # noqa: E402
from app.db import cursor, init_db  # noqa: E402
from app.services import homebank_verificacion as hv  # noqa: E402
from app.services.categorizer import resolve_category  # noqa: E402

init_db()
D = Decimal
DESDE, HASTA = date(2026, 1, 1), date(2026, 3, 15)


class _Base(unittest.TestCase):
    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        with cursor() as cur:
            self.super = resolve_category(cur, "Alimentación|Supermercados y alimentación")
            self.traspaso = resolve_category(cur, "Transferencias|Traspaso entre cuentas")
            cur.execute("INSERT INTO accounts(name, type, initial_balance) VALUES ('Banco', 'bank', 1000)")
            self.banco = cur.lastrowid
            # El fondo vale lo que diga su valoración: una aportación no mueve su saldo.
            cur.execute("INSERT INTO accounts(name, type, initial_balance) VALUES ('Fondo', 'investment', 4000)")
            self.fondo = cur.lastrowid
            cur.execute("INSERT INTO account_valuations(account_id, date, value) VALUES (?, '2025-12-31', 5000)",
                        (self.fondo,))
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, category_id, hash) "
                        "VALUES (?, '2026-02-10', -40, 'Compra', ?, 'v-1')", (self.banco, self.super))
            self.compra = cur.lastrowid
        self.ruta_despues = os.path.join(_TMP, "despues.db")
        origen = sqlite3.connect(DB_PATH)
        destino = sqlite3.connect(self.ruta_despues)
        origen.backup(destino)
        origen.close()
        self.antes = sqlite3.connect(DB_PATH)
        self.despues = destino
        for con in (self.antes, self.despues):
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON")

    def tearDown(self):
        self.antes.close()
        self.despues.close()
        os.remove(self.ruta_despues)
        self._vaciar()

    def _vaciar(self):
        with cursor() as cur:
            for tabla in ("account_valuations", "transactions", "accounts", "category_rules"):
                cur.execute(f"DELETE FROM {tabla}")
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def _comparar(self):
        return hv.comparar(self.antes.cursor(), self.despues.cursor(), DESDE, HASTA)


class TestComparar(_Base):
    def test_dos_bases_iguales_son_identicas(self):
        informe = self._comparar()
        self.assertTrue(informe.identico)
        self.assertEqual(informe.meses, ["2026-01", "2026-02", "2026-03"])

    def test_historia_anterior_con_su_saldo_inicial_no_cambia_nada(self):
        # Lo que hace la carga: un movimiento de 2025 y el saldo inicial que
        # retrocede lo mismo. Dentro del periodo comparado, todo igual.
        self.despues.execute("INSERT INTO transactions(account_id, date, amount, description, hash) "
                             "VALUES (?, '2025-06-01', 300, 'Nómina', 'homebank:2025:x')", (self.banco,))
        self.despues.execute("UPDATE accounts SET initial_balance = 700 WHERE id = ?", (self.banco,))
        self.assertTrue(self._comparar().identico)

    def test_un_saldo_inicial_cambiado_se_ve_en_cada_cierre(self):
        self.despues.execute("UPDATE accounts SET initial_balance = 1001 WHERE id = ?", (self.banco,))
        informe = self._comparar()
        self.assertFalse(informe.identico)
        self.assertEqual({(d.fecha, d.antes, d.despues) for d in informe.saldos if d.cuenta == self.banco},
                         {("2026-01-31", D("1000.00"), D("1001.00")), ("2026-02-28", D("960.00"), D("961.00")),
                          ("2026-03-15", D("960.00"), D("961.00"))})
        self.assertEqual(len(informe.patrimonio), 3)

    def test_un_gasto_que_pasa_a_traspaso_se_ve_en_su_mes(self):
        self.despues.execute("INSERT INTO transactions(account_id, date, amount, description, hash, transfer_id) "
                             "VALUES (?, '2026-02-10', 40, 'Compra', 'v-2', ?)", (self.fondo, self.compra))
        pareja = self.despues.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.despues.execute("UPDATE transactions SET transfer_id = ?, category_id = ? WHERE id = ?",
                             (pareja, self.traspaso, self.compra))
        informe = self._comparar()
        self.assertEqual([(k.mes, k.que, k.antes, k.despues) for k in informe.kpis],
                         [("2026-02", "gastos", D("-40.00"), D("0.00"))])

    def test_categorias_nuevas_y_perdidas(self):
        self.despues.execute("INSERT INTO categories(name, kind) VALUES ('Inventada', 'expense')")
        informe = self._comparar()
        self.assertEqual(informe.categorias_nuevas, ["Inventada"])
        self.assertEqual(informe.categorias_perdidas, [])


class TestReglas(_Base):
    def _fruteria(self):
        for i in range(3):
            self.despues.execute("INSERT INTO transactions(account_id, date, amount, description, category_id, "
                                 "hash) VALUES (?, '2025-05-01', -9, 'FRUTERIA PEPITO', ?, ?)",
                                 (self.banco, self.super, f"homebank:2025:{i}"))

    def test_avisa_de_las_reglas_que_aprenderia_la_proxima_importacion(self):
        self._fruteria()
        self.despues.commit()
        nuevas, revocadas = hv.reglas_que_cambiarian(self.antes, self.despues)
        self.assertIn(("FRUTERIA", "Alimentación › Supermercados y alimentación"), nuevas)
        self.assertEqual(revocadas, [])
        # Y no las escribe: solo avisa.
        self.assertIsNone(self.despues.execute(
            "SELECT 1 FROM category_rules WHERE pattern = 'FRUTERIA'").fetchone())

    def test_con_cambios_sin_confirmar_avisa_en_vez_de_quedarse_esperando(self):
        # SQLite no deja copiar una base a medio escribir desde su propia
        # conexión; sin este aviso, la copia reintentaría para siempre.
        self._fruteria()
        with self.assertRaisesRegex(ValueError, "sin confirmar"):
            hv.reglas_que_cambiarian(self.antes, self.despues)


if __name__ == "__main__":
    unittest.main()
