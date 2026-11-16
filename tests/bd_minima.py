"""
Una base SQLite en memoria con lo justo para probar saldos y agregados: cuentas,
valoraciones y movimientos. La comparten los tests de balances.py y de
analytics.py, que no necesitan el esquema entero ni tocar el disco.
"""
import sqlite3


def nueva_bd() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'bank',
            initial_balance REAL NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE account_valuations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            note TEXT,
            UNIQUE(account_id, date)
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            transfer_id INTEGER
        );
    """)
    return con
