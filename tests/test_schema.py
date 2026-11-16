"""
Tests del arranque de la base: crearla de cero y poner al día una antigua.

`init_db()` corre en cada arranque, contra la base de verdad. Tiene que servir
igual para una base nueva, para una de hace meses a la que le faltan columnas
y para la de ayer, a la que no le falta nada: sin perder un dato y sin fallar
la segunda vez.

Cada test arranca sobre su propio fichero temporal, no sobre la base que
comparten los demás tests. Datos inventados.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="tnt-schema-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "schema.db")

from app import db  # noqa: E402
from app.schema import DEFAULT_CATEGORIES  # noqa: E402

TABLAS = {"accounts", "categories", "transactions", "budgets", "category_rules", "settings",
          "external_transfer_rules", "reconciliations", "import_batches", "account_valuations",
          "description_aliases"}

# Como eran estas dos tablas antes de que existieran los lotes de importación
# y el importe exacto de las reglas de transferencia.
BASE_ANTIGUA = """
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, bank TEXT, iban TEXT,
    type TEXT NOT NULL DEFAULT 'bank', initial_balance REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR', archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL, date TEXT NOT NULL,
    value_date TEXT, amount REAL NOT NULL, description TEXT NOT NULL, memo TEXT,
    category_id INTEGER, auto_categorized INTEGER NOT NULL DEFAULT 0, confidence REAL,
    transfer_id INTEGER, payee TEXT, balance REAL, source_hint TEXT,
    hash TEXT NOT NULL UNIQUE, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE external_transfer_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT NOT NULL, source_account_id INTEGER,
    target_account_id INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pattern, source_account_id, target_account_id));
INSERT INTO accounts(id, name, iban) VALUES
    (1, 'Con espacios', 'es00 1111 2222 3333 4444 5555'),
    (2, 'Con tabulador', 'ES00\t9999\t8888'),
    (3, 'Ya bien', 'ES0012345678'),
    (4, 'Sin IBAN', NULL);
INSERT INTO transactions(id, account_id, date, amount, description, hash)
    VALUES (1, 1, '2025-03-01', -12.5, 'COMPRA DE ANTES', 'hash-antiguo');
INSERT INTO external_transfer_rules(id, pattern, target_account_id) VALUES (1, 'aportacion', 2);
"""


class _Arranque(unittest.TestCase):
    def setUp(self):
        fd, ruta = tempfile.mkstemp(suffix=".db", dir=_TMP)
        os.close(fd)
        os.remove(ruta)                       # una base nueva empieza sin fichero
        self.ruta = Path(ruta)

    def arrancar(self):
        with mock.patch.object(db, "DB_PATH", self.ruta):
            db.init_db()

    def abrir(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.ruta)
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con

    @staticmethod
    def columnas(con, tabla) -> set[str]:
        return {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}

    @staticmethod
    def nombres(con, tipo) -> set[str]:
        return {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type = ?", (tipo,))}


class TestBaseNueva(_Arranque):
    def test_tiene_todas_las_tablas(self):
        self.arrancar()
        self.assertEqual(TABLAS - self.nombres(self.abrir(), "table"), set())

    def test_los_movimientos_llevan_su_lote_y_las_reglas_su_importe(self):
        # Las dos columnas que se añadieron después están también en una base nueva.
        self.arrancar()
        con = self.abrir()
        self.assertIn("import_batch_id", self.columnas(con, "transactions"))
        self.assertIn("amount", self.columnas(con, "external_transfer_rules"))
        self.assertIn("idx_tx_batch", self.nombres(con, "index"))

    def test_trae_el_arbol_de_categorias_de_siembra(self):
        self.arrancar()
        con = self.abrir()
        esperadas = sum(1 + len(subs) for _, _, subs in DEFAULT_CATEGORIES)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM categories").fetchone()[0], esperadas)
        hija = con.execute(
            "SELECT h.kind AS de_la_hija, p.name AS madre, p.kind AS de_la_madre FROM categories h "
            "JOIN categories p ON p.id = h.parent_id WHERE h.name = 'Nómina o Pensión'").fetchone()
        self.assertEqual(tuple(hija), ("income", "Nómina y otras prestaciones", "income"))

    def test_dos_principales_no_pueden_llamarse_igual(self):
        self.arrancar()
        con = self.abrir()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO categories(name, kind) VALUES ('HOGAR', 'expense')")

    def test_va_en_modo_wal(self):
        self.arrancar()
        self.assertEqual(self.abrir().execute("PRAGMA journal_mode").fetchone()[0], "wal")


class TestArrancarOtraVez(_Arranque):
    def test_la_segunda_vez_ni_falla_ni_duplica(self):
        self.arrancar()
        antes = self.abrir().execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        self.arrancar()
        self.assertEqual(self.abrir().execute("SELECT COUNT(*) FROM categories").fetchone()[0], antes)

    def test_no_resiembra_las_categorias_que_el_usuario_borro(self):
        self.arrancar()
        con = self.abrir()
        con.execute("DELETE FROM categories WHERE name != 'Sin categoría'")
        con.commit()
        self.arrancar()
        self.assertEqual([r["name"] for r in con.execute("SELECT name FROM categories")], ["Sin categoría"])


class TestBaseAntigua(_Arranque):
    def setUp(self):
        super().setUp()
        con = sqlite3.connect(self.ruta)
        con.executescript(BASE_ANTIGUA)
        con.close()

    def test_gana_las_columnas_que_le_faltan_sin_perder_lo_que_tenia(self):
        self.arrancar()
        con = self.abrir()
        mov = con.execute("SELECT description, amount, import_batch_id FROM transactions").fetchall()
        self.assertEqual([tuple(m) for m in mov], [("COMPRA DE ANTES", -12.5, None)])
        regla = con.execute("SELECT pattern, amount FROM external_transfer_rules").fetchall()
        self.assertEqual([tuple(r) for r in regla], [("aportacion", None)])
        self.assertEqual(TABLAS - self.nombres(con, "table"), set())

    def test_los_iban_quedan_sin_espacios_y_en_mayusculas(self):
        # Con espacios, el IBAN de la cuenta no casaba con el del extracto y
        # cada importación creaba la cuenta otra vez.
        self.arrancar()
        iban = dict(self.abrir().execute("SELECT name, iban FROM accounts"))
        self.assertEqual(iban, {"Con espacios": "ES0011112222333344445555", "Con tabulador": "ES0099998888",
                                "Ya bien": "ES0012345678", "Sin IBAN": None})

    def test_arrancarla_dos_veces_tampoco_falla(self):
        self.arrancar()
        self.arrancar()
        self.assertIn("import_batch_id", self.columnas(self.abrir(), "transactions"))


if __name__ == "__main__":
    unittest.main()
