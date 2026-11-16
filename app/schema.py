"""
Cómo es la base de TNT, y cómo se pone al día una que viene de antes.

Las tablas se crean con IF NOT EXISTS y las columnas que llegaron después se
añaden comprobando antes si están: `poner_al_dia()` corre en cada arranque,
contra la base de verdad, y tiene que valer igual para una base nueva, para
una de hace meses y para la de ayer.
"""
import sqlite3

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    bank            TEXT,
    iban            TEXT,
    type            TEXT    NOT NULL DEFAULT 'bank',
    initial_balance REAL    NOT NULL DEFAULT 0,
    currency        TEXT    NOT NULL DEFAULT 'EUR',
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    parent_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    kind       TEXT    NOT NULL DEFAULT 'expense',  -- 'expense' | 'income'
    icon       TEXT,
    color      TEXT,
    UNIQUE(name, parent_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id       INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date             TEXT    NOT NULL,                        -- ISO YYYY-MM-DD
    value_date       TEXT,
    amount           REAL    NOT NULL,                        -- negativo = gasto
    description      TEXT    NOT NULL,
    memo             TEXT,
    category_id      INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    auto_categorized INTEGER NOT NULL DEFAULT 0,
    confidence       REAL,
    transfer_id      INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    payee            TEXT,
    balance          REAL,
    source_hint      TEXT,                                    -- categoría original del banco
    hash             TEXT    NOT NULL UNIQUE,
    imported_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_account  ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
-- Los duplicados del panel se buscan por cuenta e importe (ver SQL_DUPLICADOS).
CREATE INDEX IF NOT EXISTS idx_tx_account_amount ON transactions(account_id, amount);

CREATE TABLE IF NOT EXISTS budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    monthly_limit REAL    NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    UNIQUE(category_id)
);

CREATE TABLE IF NOT EXISTS category_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT    NOT NULL,                        -- palabras enteras de la descripción, en MAYÚSCULAS
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    priority    INTEGER NOT NULL DEFAULT 100,
    source      TEXT    NOT NULL DEFAULT 'manual',       -- 'manual' | 'learned'
    hits        INTEGER NOT NULL DEFAULT 0,
    UNIQUE(pattern, category_id)
);

CREATE INDEX IF NOT EXISTS idx_rules_pattern ON category_rules(pattern);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Reglas para reflejar automáticamente salidas de una cuenta como
-- entradas en otra cuenta "externa" (p. ej. plan de pensiones INDEXA).
-- Cuando se importa una transacción cuya descripción contiene `pattern`,
-- se crea una transacción espejo con importe opuesto en `target_account_id`
-- y se enlazan mediante `transfer_id`.
CREATE TABLE IF NOT EXISTS external_transfer_rules (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern           TEXT    NOT NULL,                               -- subcadena en descripción (lowercase)
    source_account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,  -- NULL = cualquier cuenta
    target_account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    -- Importe exacto (en valor absoluto) que debe tener el movimiento, o NULL
    -- para cualquiera. Distingue reglas con la misma descripción: los dos
    -- depósitos de EuroCaja se llaman igual y solo difieren en el importe.
    amount            REAL,
    active            INTEGER NOT NULL DEFAULT 1,
    note              TEXT,
    created_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pattern, source_account_id, target_account_id)
);

CREATE INDEX IF NOT EXISTS idx_ext_rules_active ON external_transfer_rules(active);

-- Historial de reconciliaciones contra el saldo real del banco.
-- Cada fila registra qué decía el banco en una fecha concreta,
-- qué decía TNT, y la diferencia. Sirve para detectar movimientos
-- perdidos o duplicados al importar.
CREATE TABLE IF NOT EXISTS reconciliations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date         TEXT    NOT NULL,
    bank_balance REAL    NOT NULL,
    tnt_balance  REAL    NOT NULL,
    diff         REAL    NOT NULL,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recon_account ON reconciliations(account_id, date DESC);

-- Lotes de importación. Cada importación de uno o varios ficheros crea
-- un único batch; las transacciones nuevas guardan ese `import_batch_id`
-- para permitir deshacer todo el lote en un click.
CREATE TABLE IF NOT EXISTS import_batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    files        TEXT    NOT NULL,    -- JSON: [{"filename": ..., "bank": ..., "account": ..., "inserted": N, "duplicates": M}, ...]
    inserted     INTEGER NOT NULL DEFAULT 0,
    duplicates   INTEGER NOT NULL DEFAULT 0
);

-- Valoraciones declaradas de cuentas de inversión (fondos, planes...).
-- Un fondo cambia de valor sin que haya movimientos: la revalorización no
-- es un apunte. Por eso su saldo NO se calcula sumando movimientos, sino
-- tomando la última valoración que el usuario declara al recibir el
-- informe de la entidad. Los movimientos siguen registrando lo aportado
-- y lo reembolsado, para poder calcular la rentabilidad.
CREATE TABLE IF NOT EXISTS account_valuations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date       TEXT    NOT NULL,               -- ISO YYYY-MM-DD
    value      REAL    NOT NULL,               -- valor declarado por la entidad
    note       TEXT,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, date)
);

CREATE INDEX IF NOT EXISTS idx_valuations_account
    ON account_valuations(account_id, date DESC);

-- Alias de descripciones: cuando la descripción del banco contiene `pattern`
-- (subcadena en mayúsculas), se muestra `alias` en la UI. La descripción
-- original NO se modifica en la BD: el alias es solo cosmético.
CREATE TABLE IF NOT EXISTS description_aliases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT    NOT NULL UNIQUE,    -- subcadena en MAYÚSCULAS
    alias      TEXT    NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# Jerarquía de categorías inspirada en la que ya usa ING,
# para que la importación encaje de entrada sin re-mapear.
DEFAULT_CATEGORIES: list[tuple[str, str, list[str]]] = [
    # (nombre, tipo, subcategorías)
    ("Alimentación", "expense", [
        "Supermercados y alimentación", "Comida a domicilio"
    ]),
    ("Ocio y viajes", "expense", [
        "Cafeterías y restaurantes", "Cine, teatro y espectáculos",
        "Viajes y hoteles"
        # «Deporte y gimnasio» vive en «Educación y salud», la de ING: sembrarla
        # aquí también la repetía. Decidido por el usuario.
    ]),
    ("Hogar", "expense", [
        "Luz y gas", "Agua", "Internet y teléfono", "Comunidad",
        "Mantenimiento del hogar", "Decoración y mobiliario",
        "Seguros del hogar", "Alquiler / Hipoteca"
    ]),
    ("Transporte", "expense", [
        "Combustible", "Transporte público", "Parking y peajes",
        "Seguro coche", "Mantenimiento vehículo"
    ]),
    ("Salud", "expense", ["Farmacia", "Médicos", "Seguros de salud"]),
    ("Compras", "expense", [
        "Ropa y calzado", "Belleza, peluquería y perfumería",
        "Electrónica", "Compras (otros)"
    ]),
    ("Educación y cultura", "expense", ["Libros", "Cursos", "Suscripciones"]),
    ("Impuestos y comisiones", "expense", [
        "Impuestos", "Comisiones bancarias"
    ]),
    ("Regalos y donaciones", "expense", []),
    # Ni «Bizum enviado» ni las transferencias se siembran aquí: viven en el
    # árbol de ING («Otros gastos», «Movimientos excluidos») y las crean las
    # reglas integradas (ver _BUILTIN en categorizer). Sembrarlas también las
    # duplicaba en dos sitios.
    ("Sin categoría", "expense", []),

    ("Nómina y otras prestaciones", "income", [
        "Nómina o Pensión", "Desempleo", "Otros ingresos"
    ]),
    ("Ventajas ING", "income", ["Abono de intereses", "Devoluciones"]),
    ("Ingresos varios", "income", ["Bizum recibido", "Reembolsos"]),
]


def poner_al_dia(cur: sqlite3.Cursor) -> None:
    """Crea las tablas que falten, migra lo antiguo y, si no hay ninguna
    categoría, siembra las de partida.

    OJO: executescript() confirma por su cuenta antes de ejecutar, así que esto
    no es una transacción entera. No pasa nada: son pasos que se pueden repetir,
    no una operación de dinero.
    """
    cur.executescript(SCHEMA)
    _add_columns_if_missing(cur)
    _normalize_account_ibans(cur)
    _seed_categories(cur)
    _indice_principales(cur)


def _add_columns_if_missing(cur: sqlite3.Cursor) -> None:
    """Migraciones puntuales: añadir columnas a tablas existentes
    cuando el esquema evoluciona. SQLite no permite IF NOT EXISTS en
    ALTER TABLE, así que comprobamos PRAGMA primero."""
    cols = {row["name"] for row in cur.execute("PRAGMA table_info(transactions)")}
    if "import_batch_id" not in cols:
        cur.execute(
            "ALTER TABLE transactions ADD COLUMN import_batch_id "
            "INTEGER REFERENCES import_batches(id) ON DELETE SET NULL"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_batch ON transactions(import_batch_id)"
        )

    cols = {row["name"] for row in cur.execute("PRAGMA table_info(external_transfer_rules)")}
    if "amount" not in cols:
        cur.execute("ALTER TABLE external_transfer_rules ADD COLUMN amount REAL")


def _normalize_account_ibans(cur: sqlite3.Cursor) -> None:
    """Quita espacios/tabs y pasa a mayúsculas los IBANs de la tabla accounts.

    Versiones antiguas guardaban el IBAN con espacios tal cual lo tecleaba
    el usuario. El importer normaliza sin espacios, así que el lookup por
    IBAN no matcheaba y se duplicaba la cuenta al importar. Esta migración
    deja todos los IBANs en formato canónico.
    """
    cur.execute(
        "UPDATE accounts "
        "SET iban = REPLACE(REPLACE(UPPER(iban), ' ', ''), CHAR(9), '') "
        "WHERE iban IS NOT NULL "
        "  AND iban != REPLACE(REPLACE(UPPER(iban), ' ', ''), CHAR(9), '')"
    )


def _seed_categories(cur: sqlite3.Cursor) -> None:
    if cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0] > 0:
        return
    for name, kind, subs in DEFAULT_CATEGORIES:
        cur.execute(
            "INSERT INTO categories(name, kind) VALUES (?, ?)",
            (name, kind),
        )
        parent_id = cur.lastrowid
        for sub in subs:
            cur.execute(
                "INSERT INTO categories(name, parent_id, kind) VALUES (?, ?, ?)",
                (sub, parent_id, kind),
            )


def _indice_principales(cur: sqlite3.Cursor) -> None:
    """Dos categorías principales no pueden llamarse igual. `UNIQUE(name,
    parent_id)` no lo impide: en las principales `parent_id` es nulo, y en SQLite
    dos nulos nunca chocan. Sin mayúsculas, como las busca `resolve_category`.

    Si una base ya las tuviera repetidas, crear el índice fallaría y la app no
    arrancaría: entonces no se crea."""
    repetidas = cur.execute(
        "SELECT 1 FROM categories WHERE parent_id IS NULL "
        "GROUP BY name COLLATE NOCASE HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone()
    if repetidas is None:
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_categorias_principales "
            "ON categories(name COLLATE NOCASE) WHERE parent_id IS NULL"
        )
