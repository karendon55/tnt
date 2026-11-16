"""
Capa de datos SQLite para TNT: la conexión y las transacciones.
Cómo es la base (tablas, migraciones, categorías de siembra) está en schema.py.
"""
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import DB_PATH
from app.schema import poner_al_dia


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor(inmediata: bool = False) -> Iterator[sqlite3.Cursor]:
    """Un cursor y, con él, UNA transacción.

    La conexión va en autocommit, así que cada sentencia se confirmaría sola.
    En una app de dinero eso es peligroso: enlazar un traspaso son dos UPDATE,
    y crear un movimiento espejo es un INSERT más dos UPDATE. Si algo falla en
    medio y cada sentencia ya se ha confirmado, queda un traspaso enlazado por
    un solo lado, o un ingreso que aparece de la nada en el saldo.

    Poniendo la transacción aquí, las cincuenta y pico llamadas la heredan y no
    hay que acordarse en cada una. Un bloque que solo lee abre una transacción
    diferida, que en SQLite no bloquea nada hasta la primera lectura.

    Para lotes donde un elemento malo no debe tirar los buenos, ver savepoint().

    Con `inmediata`, la transacción pide la escritura desde el principio
    (`BEGIN IMMEDIATE`). Hace falta cuando se lee para decidir si escribir:
    en modo WAL, otra petición que haya escrito entre medias deja la lectura
    vieja, y la escritura falla con «database is locked». Así, la segunda
    espera y lee ya lo que escribió la primera.
    """
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE" if inmediata else "BEGIN")
        try:
            yield cur
        except BaseException:
            # `executescript()` y algún DDL confirman por su cuenta y cierran
            # la transacción; entonces no hay nada que deshacer y pedirlo sería
            # un error encima del error.
            if conn.in_transaction:
                cur.execute("ROLLBACK")
            raise
        else:
            if conn.in_transaction:
                cur.execute("COMMIT")
    finally:
        conn.close()


@contextmanager
def savepoint(cur: sqlite3.Cursor, nombre: str) -> Iterator[sqlite3.Cursor]:
    """Transacción anidada dentro de un `cursor()`.

    Sirve para trabajos por lotes: al importar varios ficheros, uno que falle a
    medias debe deshacer lo suyo sin arrastrar a los que ya entraron bien.

    El nombre se usa tal cual en el SQL, así que solo se admiten letras, cifras
    y guión bajo: nunca viene de fuera, pero más vale cerrarlo.
    """
    if not nombre.replace("_", "").isalnum():
        raise ValueError(f"nombre de savepoint no válido: {nombre!r}")
    cur.execute(f"SAVEPOINT {nombre}")
    try:
        yield cur
    except BaseException:
        cur.execute(f"ROLLBACK TO {nombre}")
        cur.execute(f"RELEASE {nombre}")
        raise
    else:
        cur.execute(f"RELEASE {nombre}")


@contextmanager
def db_snapshot(src: Path | str = DB_PATH) -> Iterator[Path]:
    """Copia consistente de la BD en un fichero temporal, vía la API de
    backup de SQLite.

    Con journal_mode=WAL, las transacciones confirmadas viven en el
    fichero -wal hasta el checkpoint; copiar tnt.db a pelo puede perder
    los últimos movimientos o pillar un checkpoint a medias. La API de
    backup produce un snapshot íntegro aunque la app esté escribiendo.

    El temporal se borra al salir del contexto.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="tnt-snapshot-"))
    snap = tmp_dir / "tnt.db"
    try:
        src_conn = sqlite3.connect(src)
        try:
            dst_conn = sqlite3.connect(snap)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        yield snap
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def init_db() -> None:
    """Deja la base lista para usarse: la crea si no existe y la pone al día."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with cursor() as cur:
        poner_al_dia(cur)
