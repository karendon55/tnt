"""
Router /importar — formulario y procesado de extractos bancarios.

Flujo:
  GET  /importar          -> muestra formulario de subida
  POST /importar          -> procesa uno o varios ficheros, dedup, aprende reglas
"""
from __future__ import annotations

import tempfile
import traceback
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse

from app.db import cursor
from app.importers.dispatcher import detect_and_parse
from app.services.categorizer import retrain_and_apply
from app.services.ingest import ingest
from app.templating import templates

router = APIRouter()


@router.get("/importar", response_class=HTMLResponse)
def import_form(request: Request):
    return templates.TemplateResponse(
        request, "import.html", {"active": "import"}
    )


@router.post("/importar", response_class=HTMLResponse)
async def import_post(request: Request, files: list[UploadFile] = File(...)):
    results: list[dict] = []
    errors: list[dict] = []

    for up in files:
        if not up.filename:
            continue
        suffix = Path(up.filename).suffix or ".xls"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(await up.read())
            tmp.close()
            extract = detect_and_parse(Path(tmp.name))
            with cursor() as cur:
                cur.execute("BEGIN")
                try:
                    r = ingest(cur, extract)
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
            results.append({
                "filename": up.filename,
                "bank": extract.bank,
                "account": r.account_name,
                "total": r.total_rows,
                "inserted": r.inserted,
                "duplicates": r.duplicates,
                "from_hint": r.categorized_from_hint,
                "transfers": r.transfers_linked,
            })
        except Exception as exc:
            errors.append({
                "filename": up.filename,
                "message": str(exc) or exc.__class__.__name__,
                "trace": traceback.format_exc(limit=2),
            })
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    rules_created = 0
    auto_applied = 0
    if results:
        with cursor() as cur:
            cur.execute("BEGIN")
            try:
                rules_created, auto_applied = retrain_and_apply(cur)
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    total_inserted = sum(r["inserted"] for r in results)
    total_dup = sum(r["duplicates"] for r in results)
    total_transfers = sum(r["transfers"] for r in results)
    total_hint = sum(r["from_hint"] for r in results)

    return templates.TemplateResponse(
        request,
        "import_result.html",
        {
            "active": "import",
            "results": results,
            "errors": errors,
            "summary": {
                "files": len(results),
                "inserted": total_inserted,
                "duplicates": total_dup,
                "transfers": total_transfers,
                "categorized_hint": total_hint,
                "rules_created": rules_created,
                "auto_applied": auto_applied,
            },
            "confetti": total_inserted > 0,
        },
    )
