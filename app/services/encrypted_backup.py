"""
Backup cifrado de la base de datos.

Formato del fichero (binario):

    +-----------------------+
    |  "TNT1\n"   (5 bytes) |   magic + versión
    |  iters    (4 bytes BE)|   nº de iteraciones PBKDF2
    |  salt     (16 bytes)  |   sal aleatoria
    |  fernet_token (...)   |   payload cifrado con Fernet
    +-----------------------+

`fernet_token` cifra los bytes crudos de la base de datos SQLite usando una clave
derivada de la contraseña con PBKDF2-HMAC-SHA256 (iteraciones configurables,
por defecto 480 000 — recomendación OWASP 2023). Fernet firma con HMAC-SHA256
así que cualquier modificación o contraseña incorrecta se detecta.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import struct
from pathlib import Path
from typing import Tuple

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"TNT1\n"
DEFAULT_ITERS = 480_000
SALT_LEN = 16


def _derive_key(password: str, salt: bytes, iters: int) -> bytes:
    """Deriva una clave Fernet (32 bytes base64-url) desde la contraseña."""
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña no puede estar vacía.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iters,
    )
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def pack(plaintext: bytes, password: str, *, iters: int = DEFAULT_ITERS) -> bytes:
    """Devuelve los bytes del fichero cifrado a partir de los bytes en claro."""
    salt = os.urandom(SALT_LEN)
    key = _derive_key(password, salt, iters)
    token = Fernet(key).encrypt(plaintext)
    header = MAGIC + struct.pack(">I", iters) + salt
    return header + token


def unpack(blob: bytes, password: str) -> bytes:
    """Devuelve los bytes en claro a partir del fichero cifrado.

    Lanza ValueError si el formato no es válido o la contraseña es incorrecta.
    """
    if not blob.startswith(MAGIC):
        raise ValueError("El fichero no parece un backup TNT cifrado.")
    cursor = len(MAGIC)
    if len(blob) < cursor + 4 + SALT_LEN + 1:
        raise ValueError("El fichero está truncado.")
    iters = struct.unpack(">I", blob[cursor:cursor + 4])[0]
    cursor += 4
    salt = blob[cursor:cursor + SALT_LEN]
    cursor += SALT_LEN
    token = blob[cursor:]

    # Defensa contra ataques con iters absurdamente altos
    if iters < 10_000 or iters > 10_000_000:
        raise ValueError(f"Número de iteraciones fuera de rango: {iters}")

    key = _derive_key(password, salt, iters)
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken as e:
        raise ValueError("Contraseña incorrecta o fichero corrupto.") from e


def pack_file(src: Path, password: str, *, iters: int = DEFAULT_ITERS) -> bytes:
    """Lee `src` y devuelve el blob cifrado."""
    src = Path(src)
    return pack(src.read_bytes(), password, iters=iters)


def _checkpoint_wal(db: Path) -> None:
    """Vuelca el -wal pendiente a la BD principal (best effort).
    Así la copia .before-restore incluye las últimas transacciones."""
    try:
        conn = sqlite3.connect(db)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def restore_file(blob: bytes, password: str, dest: Path) -> Tuple[Path, str]:
    """Descifra `blob` y escribe el resultado en `dest` de forma atómica.

    Antes de sobrescribir, deja el fichero original en `dest.before-restore-<sha8>`
    para poder volver atrás manualmente si algo va mal.

    Devuelve (ruta del backup previo, sha256 hex de los datos restaurados).
    """
    plaintext = unpack(blob, password)
    sha = hashlib.sha256(plaintext).hexdigest()
    dest = Path(dest)
    backup_prev = None
    if dest.exists():
        # Checkpoint para que la copia de seguridad previa esté completa.
        _checkpoint_wal(dest)
        backup_prev = dest.with_suffix(dest.suffix + f".before-restore-{sha[:8]}")
        # No sobrescribimos un previo si ya existe (es información de seguridad)
        if not backup_prev.exists():
            os.replace(dest, backup_prev)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(plaintext)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest)
    # El -wal/-shm de la BD anterior no debe aplicarse a la restaurada:
    # SQLite intentaría "recuperar" ese WAL viejo sobre la BD nueva.
    for suffix in ("-wal", "-shm"):
        Path(str(dest) + suffix).unlink(missing_ok=True)
    return (backup_prev or dest, sha)
