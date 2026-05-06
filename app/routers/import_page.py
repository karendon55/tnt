"""
Router /importar — preview, confirmación, listado de lotes y deshacer.

Flujo nuevo:
  GET  /importar                 -> formulario de subida.
  POST /importar                 -> parsea ficheros, calcula preview (sin tocar BD)
                                    y muestra resumen + sample. Cachea los datos
                                    parseados con un token UUID.
  POST /importar/confirmar       -> recibe token y hace la inserción real,
                                    creando un import_batch para permitir undo.
  GET  /importar/lotes           -> historial de lotes con botón "Deshacer".
  POST /importar/lotes/{id}/borrar -> borra todas las transacciones del lote.
"""
from __future__ import annotations

import json
import tempfile
import time
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.importers.dispatcher import detect_and_parse
from app.services.categorizer import retrain_and_apply
from app.services.ingest import ingest, preview
from app.templating import templates

router = APIRouter()


# Caché en proceso para previews. Token -> {expires_at, extracts: [(filename, ParsedExtract)], previews: [PreviewResult]}.
# La caché es deliberadamente in-memory: si el proceso se reinicia entre el
# preview y la confirmación, el usuario simplemente vuelve a subir.
_PREVIEW_CACHE: dict[str, dict] = {}
_PREVIEW_TTL = 600  # 10 minutos


def _gc_previews() -> None:
    now = time.time()
    expired = [k for k, v in _PREVIEW_CACHE.items() if v["expires_at"] < now]
    for k in expired:
        _PREVIEW_CACHE.pop(k, None)


@router.get("/importar", response_class=HTMLResponse)
def import_form(request: Request):
    return templates.TemplateResponse(
        request, "import.html", {"active": "import"}
    )


@router.post("/importar", response_class=HTMLResponse)
async def import_preview(request: Request, files: list[UploadFile] = File(...)):
    """Parsea, calcula el preview y deja los extractos en caché. NO inserta."""
    _gc_previews()
    parsed: list[tuple[str, object]] = []  # (filename, ParsedExtract)
    previews: list[dict] = []
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
                pv = preview(cur, extract)
            parsed.append((up.filename, extract))
            previews.append({
                "filename": up.filename,
                "bank": pv.bank,
                "account": pv.account_name,
                "iban": pv.iban,
                "total": pv.total_rows,
                "new": pv.new_rows,
                "duplicates": pv.duplicate_rows,
                "rows": [
                    {
                        "date": r.date, "amount": r.amount,
                        "description": r.description,
                        "will_insert": r.will_insert,
                        "source_hint": r.source_hint,
                    } for r in pv.rows
                ],
            })
        except Exception as exc:
            errors.append({
                "filename": up.filename,
                "message": str(exc) or exc.__class__.__name__,
                "trace": traceback.format_exc(limit=2),
            })
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    token = ""
    if parsed:
        token = uuid.uuid4().hex
        _PREVIEW_CACHE[token] = {
            "expires_at": time.time() + _PREVIEW_TTL,
            "parsed": parsed,
        }

    total_new = sum(p["new"] for p in previews)
    total_dup = sum(p["duplicates"] for p in previews)

    return templates.TemplateResponse(
        request, "import_preview.html",
        {
            "active": "import",
            "previews": previews,
            "errors": errors,
            "token": token,
            "summary": {
                "files": len(previews),
                "new": total_new,
                "duplicates": total_dup,
            },
        },
    )


@router.post("/importar/confirmar", response_class=HTMLResponse)
def import_confirm(request: Request, token: str = Form(...)):
    """Inserta los extractos cacheados como un único batch. Si el token no
    está en caché, redirige al formulario."""
    entry = _PREVIEW_CACHE.pop(token, None)
    if not entry:
        return RedirectResponse("/importar", status_code=303)

    parsed = entry["parsed"]
    results: list[dict] = []
    errors: list[dict] = []
    files_summary: list[dict] = []

    with cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute(
                "INSERT INTO import_batches(files, inserted, duplicates) VALUES ('[]', 0, 0)"
            )
            batch_id = cur.lastrowid

            for filename, extract in parsed:
                try:
                    r = ingest(cur, extract, batch_id=batch_id)
                    results.append({
                        "filename": filename,
                        "bank": extract.bank,
                        "account": r.account_name,
                        "total": r.total_rows,
                        "inserted": r.inserted,
                        "duplicates": r.duplicates,
                        "from_hint": r.categorized_from_hint,
                        "transfers": r.transfers_linked,
                    })
                    files_summary.append({
                        "filename": filename, "bank": extract.bank,
                        "account": r.account_name,
                        "inserted": r.inserted, "duplicates": r.duplicates,
                    })
                except Exception as exc:
                    errors.append({
                        "filename": filename,
                        "message": str(exc) or exc.__class__.__name__,
                    })

            total_inserted = sum(r["inserted"] for r in results)
            total_dup = sum(r["duplicates"] for r in results)
            cur.execute(
                "UPDATE import_batches SET files = ?, inserted = ?, duplicates = ? WHERE id = ?",
                (json.dumps(files_summary, ensure_ascii=False), total_inserted, total_dup, batch_id),
            )
            # Si el lote no insertó nada, lo borramos para no ensuciar el historial
            if total_inserted == 0:
                cur.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise

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
        request, "import_result.html",
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


@router.get("/importar/lotes", response_class=HTMLResponse)
def import_batches(request: Request, msg: str = ""):
    with cursor() as cur:
        rows = cur.execute(
            """SELECT b.id, b.created_at, b.files, b.inserted, b.duplicates,
                      (SELECT COUNT(*) FROM transactions t WHERE t.import_batch_id = b.id)
                          AS still_present
               FROM import_batches b
               ORDER BY b.id DESC
               LIMIT 100"""
        ).fetchall()
        batches = []
        for r in rows:
            try:
                files = json.loads(r["files"]) if r["files"] else []
            except Exception:
                files = []
            batches.append({
                "id": r["id"],
                "created_at": r["created_at"],
                "files": files,
                "inserted": r["inserted"],
                "duplicates": r["duplicates"],
                "still_present": r["still_present"],
            })
    return templates.TemplateResponse(
        request, "import_batches.html",
        {"active": "import", "batches": batches, "msg": msg},
    )


@router.post("/importar/lotes/{batch_id}/borrar")
def import_batch_delete(batch_id: int):
    """Borra todas las transacciones del lote y el lote en sí."""
    with cursor() as cur:
        cur.execute("BEGIN")
        try:
            n = cur.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE import_batch_id = ?",
                (batch_id,),
            ).fetchone()["n"]
            cur.execute("DELETE FROM transactions WHERE import_batch_id = ?", (batch_id,))
            cur.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
    return RedirectResponse(
        f"/importar/lotes?msg=Lote+%23{batch_id}+revertido+({n}+movimientos+borrados)",
        status_code=303,
    )
