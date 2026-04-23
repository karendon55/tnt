"""
Router /backup — copia data/tnt.db a rutas locales de respaldo.
Sobrescribe el fichero destino (no versiona con timestamp).
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import DB_PATH
from app.templating import templates

router = APIRouter()

# Destinos del backup. Si una ruta no existe, se crea (con sus padres).
BACKUP_DESTINATIONS = [
    Path("/home/trooper/Dropbox"),
    Path("/home/trooper/Documentos/contabilidad/backup"),
]


@router.post("/backup", response_class=HTMLResponse)
def run_backup(request: Request):
    """Copia data/tnt.db a cada destino. Sobrescribe el archivo previo."""
    src = Path(DB_PATH)
    if not src.exists():
        return templates.TemplateResponse(
            request, "_backup_status.html",
            {"ok": False, "results": [], "message": f"No existe {src}"},
        )

    results = []
    for dest_dir in BACKUP_DESTINATIONS:
        dest_file = dest_dir / "tnt.db"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_file)  # preserva mtime
            size_kb = round(dest_file.stat().st_size / 1024, 1)
            results.append({
                "dest": str(dest_file),
                "ok": True,
                "size_kb": size_kb,
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
