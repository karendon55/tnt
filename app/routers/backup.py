"""
Router /backup — copia data/tnt.db a rutas locales de respaldo.

  · POST /backup          → copia plana a TODOS los destinos locales (Dropbox, ...).
  · POST /backup/destino  → copia (plana o cifrada) a UN único destino.
  · GET  /backup          → página con todas las opciones (cifrado, restaurar).
  · POST /backup/cifrado  → descarga un .tnt cifrado con contraseña.
  · POST /backup/restaurar→ acepta un .tnt + contraseña y restaura la BD.

Sobrescribe el fichero destino (no versiona con timestamp). La lista de destinos
y la copia a cada uno están en services/backup_destinations.py.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.config import DB_PATH, DEMO_MODE
from app.db import db_snapshot
from app.services.backup_destinations import (
    backup_one,
    get_backup_destinations,
    load_destinations,
    save_destinations,
    set_backup_destinations,
)
from app.services.encrypted_backup import (
    pack_file as _pack_file,
    restore_file as _restore_file,
)
from app.services.master_key import encrypt_secret as _encrypt_secret
from app.templating import templates

router = APIRouter()

# En modo demostración los destinos configurados son los de verdad —~/Dropbox y
# la carpeta de contabilidad—, así que un backup escribiría la base de mentira
# encima de las copias buenas. Se bloquea la escritura, no la pantalla: se
# puede seguir mirando cómo está montado todo.
_AVISO_DEMO = ("Backup desactivado en modo demostración: escribiría la base de "
               "mentira encima de tus copias reales.")


def _bloqueado_por_demo(request: Request, plantilla: str = "_backup_status.html"):
    if not DEMO_MODE:
        return None
    return templates.TemplateResponse(
        request, plantilla, {"ok": False, "results": [], "message": _AVISO_DEMO},
    )


@router.post("/backup", response_class=HTMLResponse)
def run_backup(request: Request):
    """Copia data/tnt.db a cada destino aplicando el modo configurado de
    cada uno (plano o cifrado). Sobrescribe el archivo previo."""
    if (bloqueo := _bloqueado_por_demo(request)) is not None:
        return bloqueo
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_status.html",
            {"ok": False, "results": [], "message": f"No existe {src}"},
        )

    # Snapshot consistente (incluye lo pendiente en el -wal) para todos
    # los destinos, en vez de copiar tnt.db a pelo con la app escribiendo.
    with db_snapshot(src) as snap:
        results = [backup_one(snap, d) for d in get_backup_destinations()]
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
    if DEMO_MODE:
        return templates.TemplateResponse(
            request, "_backup_destino_status.html",
            {"ok": False, "dest_index": dest_index, "mode": "plain",
             "error": _AVISO_DEMO},
        )
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
        r = backup_one(snap, destinations[dest_index])
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
    dests = load_destinations()
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
    save_destinations(dests)
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
