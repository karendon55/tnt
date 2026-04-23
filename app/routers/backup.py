"""
Router /backup — copia data/tnt.db a rutas locales de respaldo.
Sobrescribe el fichero destino (no versiona con timestamp).
"""
from __future__ import annotations

import os
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
