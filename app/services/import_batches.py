"""
Lotes de importación: meter varios extractos de una vez, listarlos y deshacer uno.

Cada importación de uno o varios ficheros es un lote, y sus movimientos guardan
su `import_batch_id`: así se puede deshacer entera. Leer los ficheros y la
vista previa son cosa del router; aquí está lo que escribe.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from app.db import cursor, savepoint
from app.services.categorizer import retrain_and_apply
from app.services.ingest import ingest


@dataclass
class BatchResult:
    results: list[dict] = field(default_factory=list)  # un resumen por fichero que entró
    errors: list[dict] = field(default_factory=list)   # fichero y mensaje de los que fallaron
    rules_created: int = 0
    auto_applied: int = 0        # categorizados por reglas, de este lote
    auto_applied_otros: int = 0  # movimientos antiguos que las reglas rescataron de paso


def import_batch(parsed: list[tuple[str, object]]) -> BatchResult:
    """Inserta los extractos ya leídos —(nombre del fichero, ParsedExtract)— como
    un único lote, y después reaprende las reglas y las aplica.

    Son dos transacciones a propósito: si reaprender fallara, lo importado ya
    está dentro.
    """
    lote = BatchResult()
    results, errors = lote.results, lote.errors
    files_summary: list[dict] = []

    with cursor() as cur:
        cur.execute(
            "INSERT INTO import_batches(files, inserted, duplicates) VALUES ('[]', 0, 0)"
        )
        batch_id = cur.lastrowid

        for i, (filename, extract) in enumerate(parsed):
            # Un savepoint por fichero: si uno revienta a mitad, se deshacen
            # SUS filas y los demás siguen entrando. Sin esto, un fichero a
            # medio importar dejaba sus movimientos dentro del lote.
            try:
                with savepoint(cur, f"fichero_{i}"):
                    r = ingest(cur, extract, batch_id=batch_id)
                results.append({
                    "filename": filename,
                    "bank": extract.bank,
                    "account": r.account_name,
                    "total": r.total_rows,
                    "inserted": r.inserted,
                    "duplicates": r.duplicates,
                    "from_hint": r.categorized_from_hint,
                    "from_rule": r.categorized_from_rule,
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

    if results:
        with cursor() as cur:
            lote.rules_created, aplicadas, lote.auto_applied = retrain_and_apply(
                cur, batch_id=batch_id)
            lote.auto_applied_otros = aplicadas - lote.auto_applied
    # Lo que una regla manual categorizó al entrar también es «por reglas».
    lote.auto_applied += sum(r["from_rule"] for r in results)
    return lote


def list_batches(cur: sqlite3.Cursor) -> list[dict]:
    """Los últimos cien lotes, del más reciente al más antiguo, con cuántos de
    sus movimientos siguen en la base."""
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
    return batches


def delete_batch(cur: sqlite3.Cursor, batch_id: int) -> int:
    """Deshace un lote: borra sus movimientos y el lote. Devuelve cuántos
    movimientos se han borrado.

    Son dos DELETE: o los dos o ninguno. La transacción es la del `cursor()`
    de quien llama.
    """
    n = cur.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE import_batch_id = ?",
        (batch_id,),
    ).fetchone()["n"]
    cur.execute("DELETE FROM transactions WHERE import_batch_id = ?", (batch_id,))
    cur.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
    return n
