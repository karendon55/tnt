"""
Los destinos de backup: dónde se copia la base y cómo (tal cual o cifrada).

La lista vive en la tabla `settings`. La contraseña de un destino cifrado se
guarda cifrada con la clave maestra (master_key.py), nunca en claro. Las rutas
del backup, y el bloqueo en modo demostración, están en routers/backup.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.db import cursor
from app.services.encrypted_backup import pack_file as _pack_file
from app.services.master_key import (
    decrypt_secret as _decrypt_secret,
    encrypt_secret as _encrypt_secret,
    is_encrypted as _is_encrypted,
)

# Clave en la tabla `settings` con la lista (JSON) de destinos de backup.
# Formato: [{"path": str, "mode": "plain"|"encrypted", "password": str?}, ...]
# (el formato antiguo — lista de strings — se migra al leer).
_SETTINGS_KEY = "backup_destinations"

# Valores por defecto si la clave aún no existe.
_DEFAULT_DESTINATIONS = [
    {"path": "~/Dropbox", "mode": "plain"},
    {"path": "~/Documentos/contabilidad/backup", "mode": "plain"},
]


def _normalize_entry(entry) -> dict | None:
    """Acepta string (formato antiguo) o dict, y devuelve dict canónico."""
    if isinstance(entry, str):
        entry = {"path": entry}
    if not isinstance(entry, dict) or not str(entry.get("path", "")).strip():
        return None
    mode = entry.get("mode", "plain")
    if mode not in ("plain", "encrypted"):
        mode = "plain"
    return {
        "path": str(entry["path"]).strip(),
        "mode": mode,
        "password": entry.get("password") or None,
    }


def load_destinations() -> list[dict]:
    """Lee la configuración de destinos de `settings`. La primera vez
    siembra los valores por defecto. Migra contraseñas en texto plano
    (legacy) cifrándolas con la clave maestra y reescribiendo settings."""
    with cursor() as cur:
        row = cur.execute(
            "SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,)
        ).fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?)",
                (_SETTINGS_KEY, json.dumps(_DEFAULT_DESTINATIONS)),
            )
            raw = _DEFAULT_DESTINATIONS
        else:
            try:
                raw = json.loads(row["value"])
                if not isinstance(raw, list):
                    raw = _DEFAULT_DESTINATIONS
            except (ValueError, TypeError):
                raw = _DEFAULT_DESTINATIONS
    dests = [d for d in (_normalize_entry(e) for e in raw) if d]

    # Migración: contraseñas que estén en texto plano se cifran con la
    # clave maestra y se reescriben en BD. Idempotente.
    needs_save = False
    for d in dests:
        pwd = d.get("password")
        if pwd and not _is_encrypted(pwd):
            d["password"] = _encrypt_secret(pwd)
            needs_save = True
    if needs_save:
        save_destinations(dests)
    return dests


def save_destinations(dests: list[dict]) -> None:
    payload = []
    for d in dests:
        item = {"path": d["path"], "mode": d["mode"]}
        if d.get("password"):
            item["password"] = d["password"]
        payload.append(item)
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_SETTINGS_KEY, json.dumps(payload)),
        )


def get_backup_destinations() -> list[dict]:
    """Destinos con su config + `dir` (Path con `~` expandido)."""
    dests = load_destinations()
    for d in dests:
        d["dir"] = Path(d["path"]).expanduser()
    return dests


def set_backup_destinations(paths: list[str]) -> None:
    """Actualiza la lista de rutas (una por elemento) conservando el modo
    y la contraseña de las rutas que ya existían."""
    current: dict[str, dict] = {}
    for d in load_destinations():
        current[d["path"]] = d
        current[str(Path(d["path"]).expanduser())] = d
    new = []
    for p in paths:
        p = p.strip()
        if not p:
            continue
        new.append(current.get(p, {"path": p, "mode": "plain", "password": None}))
    save_destinations(new)


def backup_one(src: Path, dest: dict) -> dict:
    """Copia `src` a un destino según su modo configurado (plano o cifrado).

    Tras escribir el archivo del modo activo, elimina el archivo del otro
    modo si existe — así no quedan huérfanos de configuraciones anteriores
    (p.ej. un ``tnt.db`` plano viejo al lado de un ``tnt.db.tnt`` actual).

    Devuelve un dict de resultado para las plantillas de estado.
    """
    dest_dir: Path = dest["dir"]
    mode = dest["mode"]
    try:
        if mode == "encrypted" and not dest.get("password"):
            raise ValueError(
                "Modo cifrado sin contraseña configurada. "
                "Configúrala en Backup → configuración por destino."
            )
        dest_dir.mkdir(parents=True, exist_ok=True)
        if mode == "encrypted":
            password = _decrypt_secret(dest["password"])
            blob = _pack_file(src, password)
            dest_file = dest_dir / "tnt.db.tnt"
            other_file = dest_dir / "tnt.db"
            tmp = dest_file.with_suffix(dest_file.suffix + ".tmp")
            with tmp.open("wb") as fout:
                fout.write(blob)
                fout.flush()
                os.fsync(fout.fileno())
            os.replace(tmp, dest_file)
        else:
            dest_file = dest_dir / "tnt.db"
            other_file = dest_dir / "tnt.db.tnt"
            _copy_with_fsync(src, dest_file)
            if dest_file.stat().st_size != src.stat().st_size:
                raise IOError("el tamaño no coincide tras copiar")

        # Limpia huérfanos del otro modo.
        try:
            other_file.unlink(missing_ok=True)
        except OSError:
            pass

        st = dest_file.stat()
        return {
            "dest": str(dest_file),
            "ok": True,
            "mode": mode,
            "size_kb": round(st.st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S"),
        }
    except Exception as e:  # noqa: BLE001 — queremos capturar cualquier fallo de IO
        return {"dest": str(dest_dir), "ok": False, "mode": mode, "error": str(e)}


def _copy_with_fsync(src: Path, dest: Path) -> None:
    """Copia robusta: escribe a un .tmp, fsync, y rename atómico.
    Así si algo falla no dejamos un archivo medio escrito."""
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with src.open("rb") as fin, tmp.open("wb") as fout:
        while True:
            chunk = fin.read(1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)
        fout.flush()
        os.fsync(fout.fileno())
    os.replace(tmp, dest)  # rename atómico
