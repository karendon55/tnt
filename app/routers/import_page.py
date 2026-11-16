"""
Router /importar — preview, confirmación, listado de lotes y deshacer.

Flujo nuevo:
  GET  /importar                 -> formulario de subida.
  POST /importar                 -> parsea ficheros, calcula preview (sin tocar BD)
                                    y muestra resumen + sample. Cachea los datos
                                    parseados con un token UUID.
  POST /importar/confirmar       -> recibe token y hace la inserción real,
                                    creando un import_batch para permitir undo.
                                    El trabajo está en services/import_batches.py.
  GET  /importar/lotes           -> historial de lotes con botón "Deshacer".
  POST /importar/lotes/{id}/borrar -> borra todas las transacciones del lote.
"""
from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import cursor
from app.importers.dispatcher import detect_and_parse
from app.importers.homebank import _decode as _homebank_decode
from app.importers.homebank import parse_csv_text as parse_homebank_csv
from app.services.import_batches import delete_batch, import_batch, list_batches
from app.services.ingest import preview
from app.templating import templates

router = APIRouter()


# Caché en proceso para previews. Token -> {expires_at, parsed: [(filename, ParsedExtract)]}.
# La caché es deliberadamente in-memory: si el proceso se reinicia entre el
# preview y la confirmación, el usuario simplemente vuelve a subir.
_PREVIEW_CACHE: dict[str, dict] = {}
_PREVIEW_TTL = 600  # 10 minutos


def _gc_previews() -> None:
    now = time.time()
    expired = [k for k, v in _PREVIEW_CACHE.items() if v["expires_at"] < now]
    for k in expired:
        _PREVIEW_CACHE.pop(k, None)


def _vista(filename: str, bank: str, pv) -> dict:
    """Lo que la vista previa enseña de un fichero leído."""
    return {
        "filename": filename,
        "bank": bank,
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
    }


def _pagina_preview(request: Request, parsed: list, previews: list[dict], errors: list[dict]):
    """Pinta la vista previa. Si se ha leído algún fichero, lo deja en la caché
    con un token para que /importar/confirmar lo inserte."""
    token = ""
    if parsed:
        token = uuid.uuid4().hex
        _PREVIEW_CACHE[token] = {
            "expires_at": time.time() + _PREVIEW_TTL,
            "parsed": parsed,
        }
    return templates.TemplateResponse(
        request, "import_preview.html",
        {
            "active": "import",
            "previews": previews,
            "errors": errors,
            "token": token,
            "summary": {
                "files": len(previews),
                "new": sum(p["new"] for p in previews),
                "duplicates": sum(p["duplicates"] for p in previews),
            },
        },
    )


@router.get("/importar", response_class=HTMLResponse)
def import_form(request: Request):
    with cursor() as cur:
        accounts = cur.execute(
            "SELECT id, name, bank, iban FROM accounts "
            "WHERE archived = 0 ORDER BY name"
        ).fetchall()
    return templates.TemplateResponse(
        request, "import.html",
        {"active": "import", "accounts": [dict(a) for a in accounts]},
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
            previews.append(_vista(up.filename, pv.bank, pv))
        except Exception as exc:
            errors.append({
                "filename": up.filename,
                "message": str(exc) or exc.__class__.__name__,
            })
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    return _pagina_preview(request, parsed, previews, errors)


@router.post("/importar/confirmar", response_class=HTMLResponse)
def import_confirm(request: Request, token: str = Form(...)):
    """Inserta los extractos cacheados como un único batch. Si el token no
    está en caché, redirige al formulario."""
    entry = _PREVIEW_CACHE.pop(token, None)
    if not entry:
        return RedirectResponse("/importar", status_code=303)

    lote = import_batch(entry["parsed"])
    results = lote.results
    total_inserted = sum(r["inserted"] for r in results)

    return templates.TemplateResponse(
        request, "import_result.html",
        {
            "active": "import",
            "results": results,
            "errors": lote.errors,
            "summary": {
                "files": len(results),
                "inserted": total_inserted,
                "duplicates": sum(r["duplicates"] for r in results),
                "transfers": sum(r["transfers"] for r in results),
                "categorized_hint": sum(r["from_hint"] for r in results),
                "rules_created": lote.rules_created,
                "auto_applied": lote.auto_applied,
                "auto_applied_otros": lote.auto_applied_otros,
            },
            "confetti": total_inserted > 0,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
#  CSV de HomeBank
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/importar/homebank", response_class=HTMLResponse)
async def import_homebank_preview(
    request: Request,
    account_id: int = Form(...),
    file: UploadFile = File(...),
):
    """Lee un CSV de HomeBank, lo asocia a la cuenta destino indicada y muestra
    el preview. La inserción real reutiliza /importar/confirmar."""
    _gc_previews()

    # Cuenta destino (necesaria porque el CSV de HomeBank no trae IBAN)
    with cursor() as cur:
        acct = cur.execute(
            "SELECT id, name, iban, bank, currency FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    if not acct:
        return _pagina_preview(request, [], [], [{
            "filename": file.filename or "(sin nombre)",
            "message": "Cuenta destino no encontrada."}])

    blob = await file.read()
    if not blob:
        return _pagina_preview(request, [], [], [{
            "filename": file.filename or "(sin nombre)",
            "message": "El fichero está vacío."}])

    parsed: list[tuple[str, object]] = []
    previews: list[dict] = []
    errors: list[dict] = []

    try:
        text = _homebank_decode(blob)
        extract = parse_homebank_csv(
            text,
            bank=acct["bank"] or "HomeBank",
            iban=acct["iban"] or "",
            account_name=acct["name"],
            currency=acct["currency"] or "EUR",
        )
        with cursor() as cur:
            pv = preview(cur, extract)
        parsed.append((file.filename or "homebank.csv", extract))
        previews.append(_vista(file.filename or "homebank.csv", "HomeBank", pv))
        # Errores no críticos del parser (filas malformadas que se han saltado)
        parse_errors = getattr(extract, "parse_errors", None)
        if parse_errors:
            for n, msg in parse_errors[:10]:
                errors.append({
                    "filename": file.filename or "homebank.csv",
                    "message": f"línea {n}: {msg}",
                })
    except Exception as exc:
        errors.append({
            "filename": file.filename or "(sin nombre)",
            "message": str(exc) or exc.__class__.__name__,
        })

    return _pagina_preview(request, parsed, previews, errors)


@router.get("/importar/lotes", response_class=HTMLResponse)
def import_batches(request: Request, msg: str = ""):
    with cursor() as cur:
        batches = list_batches(cur)
    return templates.TemplateResponse(
        request, "import_batches.html",
        {"active": "import", "batches": batches, "msg": msg},
    )


@router.post("/importar/lotes/{batch_id}/borrar")
def import_batch_delete(batch_id: int):
    """Borra todas las transacciones del lote y el lote en sí."""
    with cursor() as cur:
        n = delete_batch(cur, batch_id)
    return RedirectResponse(
        f"/importar/lotes?msg=Lote+%23{batch_id}+revertido+({n}+movimientos+borrados)",
        status_code=303,
    )
