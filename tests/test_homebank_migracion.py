"""
Tests del paso del histórico, ya revisado, de la base de prueba a la real.

El histórico se carga en una copia de la base real; el usuario lo revisa allí
y, con su visto bueno, esto pasa a la real exactamente lo que la carga añadió
o corrigió. Lo que no puede fallar:

- La real queda como la prueba revisada: los mismos movimientos, parejas de
  traspaso, saldos iniciales y valoraciones, con lo que se recategorizó.
- Lo que se toque en la prueba fuera de la carga no pasa a la real.
- Si la real cambió en algo que la carga da por hecho (un saldo inicial, un
  movimiento de ese año, el movimiento corregido), no se migra nada. Lo de
  después, como importar el mes siguiente, no estorba.
- No se migra dos veces.

Datos inventados. La base real es temporal; la de prueba, su copia.
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from decimal import Decimal

_TMP = tempfile.mkdtemp(prefix="tnt-migracion-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "real.db")

# La base que usa cursor(): en `unittest discover` la fija el primer fichero que
# importa la configuración, así que releer TNT_DB daría otra.
from app.config import DB_PATH  # noqa: E402
from app.db import cursor, init_db  # noqa: E402
from app.importers.homebank_xhb import CuentaHB, LibroHB, OperacionHB  # noqa: E402
from app.services import homebank_historico as hh  # noqa: E402
from app.services import homebank_migracion as hm  # noqa: E402
from app.services.categorizer import resolve_category  # noqa: E402
from app.services.homebank_verificacion import comparar  # noqa: E402

init_db()
D = Decimal
ANIO = 2025


def _op(indice, fecha, importe, cuenta, categoria, descripcion):
    return OperacionHB(indice, fecha, D(importe), cuenta, categoria, descripcion, "", False)


# HomeBank: el Banco cierra 2025 en 825,30 + 175 = 1.000,30 y el banco de
# verdad dice 1.000,00 (−0,30 de discrepancia); Otro cuadra en 500.
LIBRO = LibroHB(
    cuentas={1: CuentaHB(1, "Banco", "", D("825.30"), False),
             2: CuentaHB(2, "Otro", "", D("400"), False),
             3: CuentaHB(3, "Fondo", "", D("0"), False)},
    operaciones=[_op(1, date(2025, 1, 2), "300", 1, "Sueldo", "NOMINA"),
                 _op(2, date(2025, 2, 3), "-25", 1, "Comida", "MERCADO"),
                 _op(3, date(2025, 3, 1), "-100", 1, "Ahorro", "Traspaso a Otro"),
                 _op(4, date(2025, 3, 2), "100", 2, "Ahorro", "Traspaso desde Banco")])


def _conectar(ruta):
    con = sqlite3.connect(ruta, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


class _Base(unittest.TestCase):
    def setUp(self):
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        with cursor() as cur:
            self.super = resolve_category(cur, "Alimentación|Supermercados y alimentación")
            self.restaurantes = resolve_category(cur, "Ocio y viajes|Cafeterías y restaurantes")
            self.traspaso = resolve_category(cur, "Transferencias|Traspaso entre cuentas")
            self.comisiones = resolve_category(cur, "Impuestos y comisiones|Comisiones bancarias")
            self.nomina = resolve_category(cur, "Nómina y otras prestaciones|Nómina o Pensión")
            self.ingresos = resolve_category(cur, "Nómina y otras prestaciones|Otros ingresos")
            cuentas = {}
            for nombre, tipo, inicial in (("Banco", "bank", 1000), ("Otro", "bank", 500),
                                          ("Fondo", "investment", 4000)):
                cur.execute("INSERT INTO accounts(name, type, initial_balance) VALUES (?, ?, ?)",
                            (nombre, tipo, inicial))
                cuentas[nombre] = cur.lastrowid
            self.banco, self.otro, self.fondo = cuentas["Banco"], cuentas["Otro"], cuentas["Fondo"]
            cur.execute("INSERT INTO account_valuations(account_id, date, value) VALUES (?, '2026-01-31', 4300)",
                        (self.fondo,))
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, category_id, hash) "
                        "VALUES (?, '2026-02-10', -40, 'Compra', ?, 'm-1')", (self.banco, self.super))
            self.compra = cur.lastrowid
            # Era una aportación al fondo para comisiones: la carga lo corrige.
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, category_id, hash) "
                        "VALUES (?, '2026-03-24', -120, 'Comisiones', ?, 'm-2')", (self.banco, self.comisiones))
            self.comision = cur.lastrowid
        self.ruta_prueba = os.path.join(_TMP, "prueba.db")
        self.plan = hh.Plan(
            anio=ANIO, cuentas={1: self.banco, 2: self.otro, 3: self.fondo},
            equivalencias={"Sueldo": hh.Equivalencia(self.nomina, "fija"),
                           "Comida": hh.Equivalencia(self.super, "fija"),
                           "Ahorro": hh.Equivalencia(self.traspaso, "traspaso")},
            discrepancia_gasto=self.comisiones, discrepancia_ingreso=self.ingresos,
            correcciones=(hh.Correccion(self.comision, date(2026, 3, 24), D("-120"), self.fondo, self.traspaso),),
            saldos_iniciales={self.fondo: D("3880.00")},
            valoraciones=((self.fondo, date(2025, 12, 31), D("4150.00")),))
        self.prueba = self._preparar()

    def tearDown(self):
        self.prueba.close()
        os.remove(self.ruta_prueba)
        self._vaciar()

    def _vaciar(self):
        with cursor() as cur:
            for tabla in ("account_valuations", "transactions", "accounts", "category_rules"):
                cur.execute(f"DELETE FROM {tabla}")
            cur.execute("DELETE FROM settings WHERE key LIKE 'homebank:%' OR key = 'solo-en-la-prueba'")
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def _preparar(self):
        """Lo que hará el programa: copiar la real, fotografiarla y cargar."""
        origen = sqlite3.connect(DB_PATH)
        destino = sqlite3.connect(self.ruta_prueba)
        origen.backup(destino)
        origen.close()
        destino.close()
        prueba = _conectar(self.ruta_prueba)
        prueba.execute("BEGIN")
        cur = prueba.cursor()
        hm.guardar_foto(cur, self.plan)
        hh.cargar(cur, LIBRO, self.plan)
        prueba.execute("COMMIT")
        return prueba

    def _migrar(self):
        with cursor() as real:
            return hm.migrar(self.prueba.cursor(), real, ANIO)

    def _real(self, sql, params=()):
        with cursor() as cur:
            return cur.execute(sql, params).fetchall()


class TestMigrar(_Base):
    def test_la_real_queda_como_la_prueba(self):
        resumen = self._migrar()
        self.assertEqual(resumen.movimientos, 6)  # 4 de HomeBank, la contrapartida y la discrepancia
        with cursor() as real:
            informe = comparar(self.prueba.cursor(), real, date(ANIO, 1, 1), date(2026, 12, 31))
        self.assertTrue(informe.identico, informe)
        campos = "account_id, date, amount, description, memo, category_id, source_hint, hash"
        consulta = f"SELECT {campos} FROM transactions WHERE hash LIKE 'homebank:%' ORDER BY hash"
        self.assertEqual([tuple(f) for f in self._real(consulta)],
                         [tuple(f) for f in self.prueba.execute(consulta)])

    def test_las_parejas_quedan_enlazadas_por_los_dos_lados(self):
        self._migrar()
        filas = self._real("SELECT id, amount, transfer_id FROM transactions WHERE transfer_id IS NOT NULL")
        por_id = {f["id"]: f for f in filas}
        self.assertEqual(len(filas), 4)  # el traspaso de HomeBank y la corrección
        for f in filas:
            pareja = por_id[f["transfer_id"]]
            self.assertEqual((pareja["transfer_id"], pareja["amount"]), (f["id"], -f["amount"]))

    def test_el_movimiento_corregido_pasa_a_ser_traspaso_al_fondo(self):
        self._migrar()
        (corregido,) = self._real("SELECT category_id, transfer_id FROM transactions WHERE id = ?",
                                  (self.comision,))
        self.assertEqual(corregido["category_id"], self.traspaso)
        (pareja,) = self._real("SELECT account_id, amount FROM transactions WHERE id = ?",
                               (corregido["transfer_id"],))
        self.assertEqual((pareja["account_id"], pareja["amount"]), (self.fondo, 120))

    def test_saldos_iniciales_y_valoraciones(self):
        resumen = self._migrar()
        self.assertEqual(resumen.saldos_iniciales, {self.banco: (D("1000.00"), D("825.30")),
                                                    self.otro: (D("500.00"), D("400.00")),
                                                    self.fondo: (D("4000.00"), D("3880.00"))})
        self.assertEqual(resumen.valoraciones, 1)
        self.assertEqual([tuple(f) for f in self._real(
            "SELECT date, value FROM account_valuations WHERE account_id = ? ORDER BY date", (self.fondo,))],
            [("2025-12-31", 4150.0), ("2026-01-31", 4300.0)])

    def test_respeta_lo_recategorizado_en_la_prueba(self):
        self.prueba.execute("UPDATE transactions SET category_id = ? WHERE description = 'MERCADO'",
                            (self.restaurantes,))
        self._migrar()
        self.assertEqual(self._real("SELECT category_id FROM transactions WHERE description = 'MERCADO'")[0][0],
                         self.restaurantes)

    def test_lo_tocado_en_la_prueba_fuera_de_la_carga_no_pasa(self):
        self.prueba.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (self.restaurantes, self.compra))
        self.prueba.execute("INSERT INTO category_rules(pattern, category_id) VALUES ('MERCADO', ?)", (self.super,))
        self.prueba.execute("INSERT INTO settings(key, value) VALUES ('solo-en-la-prueba', '1')")
        self._migrar()
        self.assertEqual(self._real("SELECT category_id FROM transactions WHERE id = ?", (self.compra,))[0][0],
                         self.super)
        self.assertEqual(self._real("SELECT COUNT(*) FROM category_rules")[0][0], 0)
        self.assertEqual(self._real("SELECT COUNT(*) FROM settings WHERE key = 'solo-en-la-prueba'")[0][0], 0)

    def test_lo_que_entra_despues_en_la_real_no_estorba(self):
        # Importar octubre mientras se revisa la prueba no tiene que obligar a repetirla.
        with cursor() as cur:
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, hash) "
                        "VALUES (?, '2026-10-05', -12, 'Panadería', 'm-3')", (self.banco,))
        resumen = self._migrar()
        self.assertEqual(resumen.movimientos, 6)
        self.assertEqual(self._real("SELECT COUNT(*) FROM transactions WHERE hash = 'm-3'")[0][0], 1)


class TestNoMigra(_Base):
    def _sin_cambios(self):
        self.assertEqual(self._real("SELECT COUNT(*) FROM transactions WHERE hash LIKE 'homebank:%'")[0][0], 0)
        self.assertEqual(self._real("SELECT initial_balance FROM accounts WHERE id = ?", (self.banco,))[0][0], 1000)
        self.assertEqual(self._real("SELECT category_id FROM transactions WHERE id = ?", (self.comision,))[0][0],
                         self.comisiones)

    def test_dos_veces_no(self):
        self._migrar()
        with self.assertRaisesRegex(ValueError, "ya está en la base real"):
            self._migrar()

    def test_si_la_real_cambio_un_saldo_inicial(self):
        with cursor() as cur:
            cur.execute("UPDATE accounts SET initial_balance = 1001 WHERE id = ?", (self.banco,))
        with self.assertRaisesRegex(ValueError, "«Banco»"):
            self._migrar()
        self.assertEqual(self._real("SELECT COUNT(*) FROM transactions WHERE hash LIKE 'homebank:%'")[0][0], 0)

    def test_si_la_real_tiene_un_movimiento_nuevo_de_ese_anio(self):
        with cursor() as cur:
            cur.execute("INSERT INTO transactions(account_id, date, amount, description, hash) "
                        "VALUES (?, '2025-11-05', -12, 'Olvidado', 'm-4')", (self.otro,))
        with self.assertRaisesRegex(ValueError, "«Otro»"):
            self._migrar()

    def test_si_la_real_cambio_el_movimiento_que_se_corrige(self):
        with cursor() as cur:
            cur.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (self.super, self.comision))
        with self.assertRaisesRegex(ValueError, f"movimiento {self.comision}"):
            self._migrar()

    def test_una_categoria_creada_en_la_prueba_no_existe_en_la_real(self):
        self.prueba.execute("INSERT INTO categories(name, kind) VALUES ('Inventada', 'expense')")
        nueva = self.prueba.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.prueba.execute("UPDATE transactions SET category_id = ? WHERE description = 'MERCADO'", (nueva,))
        with self.assertRaisesRegex(ValueError, "«Inventada»"):
            self._migrar()
        self._sin_cambios()

    def test_una_pareja_con_un_movimiento_que_la_carga_no_corrige(self):
        # Emparejar en la prueba un movimiento de la carga con uno de 2026 que
        # no está entre los corregidos dejaría la pareja coja en la real.
        nomina = self.prueba.execute("SELECT id FROM transactions WHERE description = 'NOMINA'").fetchone()[0]
        self.prueba.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (self.compra, nomina))
        self.prueba.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (nomina, self.compra))
        with self.assertRaisesRegex(ValueError, "emparejado"):
            self._migrar()
        self._sin_cambios()

    def test_sin_la_foto_de_la_real_no_migra(self):
        self.prueba.execute("DELETE FROM settings WHERE key LIKE 'homebank:%'")
        with self.assertRaisesRegex(ValueError, "foto"):
            self._migrar()
        self._sin_cambios()


if __name__ == "__main__":
    unittest.main()
