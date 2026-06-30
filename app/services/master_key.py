"""
Clave maestra para cifrar secretos (p.ej. contraseñas de backup) guardados en
la BD.

La clave vive en ``~/.config/tnt/master.key`` (32 bytes URL-safe base64,
permisos 600). Se genera la primera vez que se necesita.

Decisión de diseño: la clave NO se deriva de una contraseña de usuario porque
queremos que TNT pueda hacer backup automático sin pedirle nada al usuario.
Que la clave viva en ~/.config (fuera de data/tnt.db) cumple el requisito:
quien lea la BD ya no tiene la contraseña del backup cifrado.

Para reusar el formato Fernet (AES-128-CBC + HMAC-SHA256) ya en el proyecto.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Prefijo que marca un secreto cifrado con esta clave maestra.
# Cualquier secreto sin este prefijo se considera legacy (texto plano) y
# se migra al cifrarlo la primera vez que se guarda.
ENC_PREFIX = "enc:"

_KEY_PATH = Path.home() / ".config" / "tnt" / "master.key"


def _get_or_create_key() -> bytes:
    """Devuelve la clave maestra (32 bytes URL-safe base64). Si no existe,
    la genera con permisos 600."""
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes().strip()
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = Fernet.generate_key()
    # O_EXCL para evitar carrera si dos procesos arrancan a la vez.
    fd = os.open(str(_KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(ENC_PREFIX)


def encrypt_secret(plaintext: str) -> str:
    """Cifra un secreto con la clave maestra y devuelve un token con prefijo."""
    f = Fernet(_get_or_create_key())
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return ENC_PREFIX + token


def decrypt_secret(value: str) -> str:
    """Descifra un secreto cifrado por ``encrypt_secret``. Si el valor no tiene
    el prefijo, se devuelve tal cual (compat con secretos legacy en texto plano).
    """
    if not is_encrypted(value):
        return value
    f = Fernet(_get_or_create_key())
    try:
        return f.decrypt(value[len(ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        # Clave perdida o token corrupto. No queremos crashear silenciosamente
        # cuando alguien intente hacer backup — que el caller lo capture y avise.
        raise ValueError(
            "No se pudo descifrar el secreto con la clave maestra. "
            "¿Has perdido ~/.config/tnt/master.key?"
        ) from e


def key_path() -> Path:
    """Devuelve la ruta canónica del fichero de clave (para diagnóstico/UI)."""
    return _KEY_PATH
