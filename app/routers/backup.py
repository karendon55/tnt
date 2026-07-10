"""
Router /backup — copia data/tnt.db a rutas locales de respaldo.

  · POST /backup          → copia plana a TODOS los destinos locales (Dropbox, ...).
  · POST /backup/destino  → copia (plana o cifrada) a UN único destino.
  · GET  /backup          → página con todas las opciones (cifrado, restaurar).
  · POST /backup/cifrado  → descarga un .tnt cifrado con contraseña.
  · POST /backup/restaurar→ acepta un .tnt + contraseña y restaura la BD.

Sobrescribe el fichero destino (no versiona con timestamp).
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.config import DB_PATH
from app.db import cursor, db_snapshot
from app.services.encrypted_backup import (
    pack_file as _pack_file,
    restore_file as _restore_file,
)
from app.services.master_key import (
    decrypt_secret as _decrypt_secret,
    encrypt_secret as _encrypt_secret,
    is_encrypted as _is_encrypted,
)
from app.templating import templates

router = APIRouter()

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


def _load_destinations() -> list[dict]:
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
        _save_destinations(dests)
    return dests


def _save_destinations(dests: list[dict]) -> None:
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
    dests = _load_destinations()
    for d in dests:
        d["dir"] = Path(d["path"]).expanduser()
    return dests


def set_backup_destinations(paths: list[str]) -> None:
    """Actualiza la lista de rutas (una por elemento) conservando el modo
    y la contraseña de las rutas que ya existían."""
    current: dict[str, dict] = {}
    for d in _load_destinations():
        current[d["path"]] = d
        current[str(Path(d["path"]).expanduser())] = d
    new = []
    for p in paths:
        p = p.strip()
        if not p:
            continue
        new.append(current.get(p, {"path": p, "mode": "plain", "password": None}))
    _save_destinations(new)


def _backup_one(src: Path, dest: dict) -> dict:
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


@router.post("/backup", response_class=HTMLResponse)
def run_backup(request: Request):
    """Copia data/tnt.db a cada destino aplicando el modo configurado de
    cada uno (plano o cifrado). Sobrescribe el archivo previo."""
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_status.html",
            {"ok": False, "results": [], "message": f"No existe {src}"},
        )

    # Snapshot consistente (incluye lo pendiente en el -wal) para todos
    # los destinos, en vez de copiar tnt.db a pelo con la app escribiendo.
    with db_snapshot(src) as snap:
        results = [_backup_one(snap, d) for d in get_backup_destinations()]
    all_ok = all(r["ok"] for r in results)
    return templates.TemplateResponse(
        request, "_backup_status.html",
        {
            "ok": all_ok,
            "results": results,
            "ts": datetime.now().strftime("%H:%M:%S"),
        },
    )


# -----------------------------------------------------------------------
# Backup a un único destino + configuración persistente por destino
# -----------------------------------------------------------------------

@router.post("/backup/destino", response_class=HTMLResponse)
def backup_destino(request: Request, dest_index: int = Form(...)):
    """Hace backup a UN único destino usando su modo configurado.

    El backup plano se guarda como ``tnt.db``; el cifrado como ``tnt.db.tnt``.
    """
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": "plain",
             "error": f"No existe {src}"},
        )
    destinations = get_backup_destinations()
    if dest_index < 0 or dest_index >= len(destinations):
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": "plain",
             "error": "Destino inválido."},
        )

    with db_snapshot(src) as snap:
        r = _backup_one(snap, destinations[dest_index])
    ctx = {"dest_index": dest_index, "ts": datetime.now().strftime("%H:%M:%S"), **r}
    return templates.TemplateResponse(request, "_backup_destino_status.html", ctx)


@router.post("/backup/destino/config")
def backup_destino_config(
    dest_index: int = Form(...),
    mode: str = Form(...),
    password: str = Form(""),
    confirm: str = Form(""),
):
    """Guarda el modo (plano/cifrado) de un destino de forma permanente.

    Si el modo es cifrado y ya había contraseña guardada, dejar los campos
    de contraseña vacíos la mantiene. Al pasar a plano, la contraseña
    guardada se elimina.
    """
    dests = _load_destinations()
    if not (0 <= dest_index < len(dests)) or mode not in ("plain", "encrypted"):
        return RedirectResponse("/backup", status_code=303)

    d = dests[dest_index]
    if mode == "encrypted":
        if password or not d.get("password"):
            error = None
            if len(password) < 8:
                error = "La contraseña debe tener al menos 8 caracteres."
            elif password != confirm:
                error = "Las contraseñas no coinciden."
            if error:
                return RedirectResponse(
                    f"/backup?error={quote(error)}", status_code=303
                )
            d["password"] = _encrypt_secret(password)
    else:
        d["password"] = None
    d["mode"] = mode
    _save_destinations(dests)
    return RedirectResponse("/backup?saved=1", status_code=303)


# -----------------------------------------------------------------------
# Backup cifrado
# -----------------------------------------------------------------------

@router.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request, saved: str = "", error: str = ""):
    src = Path(DB_PATH)
    db_info = None
    if src.exists():
        st = src.stat()
        db_info = {
            "path": str(src),
            "size_kb": round(st.st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    destinations = [
        {"path": d["path"], "mode": d["mode"], "has_password": bool(d.get("password"))}
        for d in get_backup_destinations()
    ]
    return templates.TemplateResponse(
        request, "backup.html",
        {"active": "backup", "db_info": db_info, "destinations": destinations,
         "saved": saved == "1", "config_error": error},
    )


@router.post("/backup/destinos")
def update_destinations(destinations_text: str = Form("")):
    """Actualiza la lista de destinos de backup (una ruta por línea)."""
    set_backup_destinations(destinations_text.splitlines())
    return RedirectResponse("/backup", status_code=303)


@router.post("/backup/cifrado")
def download_encrypted(password: str = Form(...), confirm: str = Form(...)):
    """Genera un fichero .tnt cifrado con la contraseña indicada y lo devuelve
    como descarga. Exige confirmación de contraseña para evitar typos.
    """
    src = Path(DB_PATH)
    if not src.exists():
        return HTMLResponse(
            f"<p class='pill pill-warning'>No existe {src}</p>", status_code=400,
        )
    if password != confirm:
        return HTMLResponse(
            "<p class='pill pill-warning'>Las contraseñas no coinciden.</p>",
            status_code=400,
        )
    if len(password) < 8:
        return HTMLResponse(
            "<p class='pill pill-warning'>La contraseña debe tener al menos 8 caracteres.</p>",
            status_code=400,
        )
    with db_snapshot(src) as snap:
        blob = _pack_file(snap, password)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"tnt-backup-{ts}.tnt"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(blob)),
        },
    )


@router.post("/backup/restaurar", response_class=HTMLResponse)
async def restore_encrypted(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """Acepta un .tnt cifrado, lo descifra con la contraseña y reemplaza la BD
    actual de forma atómica (deja una copia previa en data/ por seguridad)."""
    blob = await file.read()
    if not blob:
        return templates.TemplateResponse(
            request, "_restore_status.html",
            {"ok": False, "error": "El fichero está vacío."},
        )
    try:
        prev_path, sha = _restore_file(blob, password, Path(DB_PATH))
    except ValueError as e:
        return templates.TemplateResponse(
            request, "_restore_status.html",
            {"ok": False, "error": str(e)},
        )
    return templates.TemplateResponse(
        request, "_restore_status.html",
        {
            "ok": True,
            "filename": file.filename,
            "sha": sha[:16],
            "previous": str(prev_path) if prev_path != Path(DB_PATH) else None,
            "ts": datetime.now().strftime("%H:%M:%S"),
        },
    )
