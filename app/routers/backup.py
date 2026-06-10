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

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.config import DB_PATH
from app.db import cursor
from app.services.encrypted_backup import (
    pack_file as _pack_file,
    restore_file as _restore_file,
)
from app.templating import templates

router = APIRouter()

# Clave en la tabla `settings` con la lista (JSON) de destinos de backup.
_SETTINGS_KEY = "backup_destinations"

# Valores por defecto si la clave aún no existe (primera ejecución tras
# la migración desde las rutas hardcodeadas).
_DEFAULT_DESTINATIONS = [
    "~/Dropbox",
    "~/Documentos/contabilidad/backup",
]


def get_backup_destinations() -> list[Path]:
    """Destinos del backup, leídos de la tabla `settings` (JSON).
    Si la clave no existe todavía, se siembra con los valores por defecto.
    Las rutas admiten `~` y se expanden aquí."""
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
    return [Path(p).expanduser() for p in raw if str(p).strip()]


def set_backup_destinations(paths: list[str]) -> None:
    """Guarda la lista de destinos (texto, una ruta por elemento) en settings."""
    clean = [p.strip() for p in paths if p.strip()]
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_SETTINGS_KEY, json.dumps(clean)),
        )


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
    """Copia data/tnt.db a cada destino. Sobrescribe el archivo previo.
    Verifica tamaño tras copiar para descartar fallos silenciosos."""
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_status.html",
            {"ok": False, "results": [], "message": f"No existe {src}"},
        )
    src_size = src.stat().st_size

    results = []
    for dest_dir in get_backup_destinations():
        dest_file = dest_dir / "tnt.db"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            _copy_with_fsync(src, dest_file)
            st = dest_file.stat()
            if st.st_size != src_size:
                raise IOError(
                    f"tamaño no coincide (origen={src_size}, destino={st.st_size})"
                )
            results.append({
                "dest": str(dest_file),
                "ok": True,
                "size_kb": round(st.st_size / 1024, 1),
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S"),
            })
        except Exception as e:  # noqa: BLE001 — queremos capturar cualquier fallo de IO
            results.append({
                "dest": str(dest_file),
                "ok": False,
                "error": str(e),
            })

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
# Backup a un único directorio (plano o cifrado)
# -----------------------------------------------------------------------

@router.post("/backup/destino", response_class=HTMLResponse)
def backup_destino(
    request: Request,
    dest_index: int = Form(...),
    mode: str = Form(...),
    password: str = Form(""),
    confirm: str = Form(""),
):
    """Hace backup a UN único destino, plano o cifrado.

    El backup plano se guarda como ``tnt.db``; el cifrado como ``tnt.db.tnt``.
    Así un mismo directorio puede tener los dos sin pisarse.
    """
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": mode,
             "error": f"No existe {src}"},
        )
    destinations = get_backup_destinations()
    if dest_index < 0 or dest_index >= len(destinations):
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": mode,
             "error": "Destino inválido."},
        )

    dest_dir = destinations[dest_index]
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if mode == "encrypted":
            if password != confirm:
                raise ValueError("Las contraseñas no coinciden.")
            if len(password) < 8:
                raise ValueError("La contraseña debe tener al menos 8 caracteres.")
            blob = _pack_file(src, password)
            dest_file = dest_dir / "tnt.db.tnt"
            tmp = dest_file.with_suffix(dest_file.suffix + ".tmp")
            with tmp.open("wb") as fout:
                fout.write(blob)
                fout.flush()
                os.fsync(fout.fileno())
            os.replace(tmp, dest_file)
        elif mode == "plain":
            dest_file = dest_dir / "tnt.db"
            _copy_with_fsync(src, dest_file)
        else:
            raise ValueError(f"Modo desconocido: {mode!r}")

        st = dest_file.stat()
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {
                "ok": True,
                "dest_index": dest_index,
                "dest": str(dest_file),
                "mode": mode,
                "size_kb": round(st.st_size / 1024, 1),
                "ts": datetime.now().strftime("%H:%M:%S"),
            },
        )
    except Exception as e:  # noqa: BLE001
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": mode, "error": str(e)},
        )


# -----------------------------------------------------------------------
# Backup cifrado
# -----------------------------------------------------------------------

@router.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request):
    src = Path(DB_PATH)
    db_info = None
    if src.exists():
        st = src.stat()
        db_info = {
            "path": str(src),
            "size_kb": round(st.st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    return templates.TemplateResponse(
        request, "backup.html",
        {"active": "backup", "db_info": db_info,
         "destinations": [str(d) for d in get_backup_destinations()]},
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
    blob = _pack_file(src, password)
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
