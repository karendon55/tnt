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
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from app.config import DB_PATH
from app.services.encrypted_backup import (
    pack_file as _pack_file,
    restore_file as _restore_file,
)
from app.templating import templates

router = APIRouter()

# Destinos del backup. Si una ruta no existe, se crea (con sus padres).
BACKUP_DESTINATIONS = [
    Path("/home/trooper/Dropbox"),
    Path("/home/trooper/Documentos/contabilidad/backup"),
]


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
    for dest_dir in BACKUP_DESTINATIONS:
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
    if dest_index < 0 or dest_index >= len(BACKUP_DESTINATIONS):
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": mode,
             "error": "Destino inválido."},
        )

    dest_dir = BACKUP_DESTINATIONS[dest_index]
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
        {"active": "backup", "db_info": db_info, "destinations": [str(d) for d in BACKUP_DESTINATIONS]},
    )


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
