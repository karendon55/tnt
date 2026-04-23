"""
Router /reglas-transferencias — gestión de reglas de transferencias externas.

Las reglas permiten que un movimiento con cierta descripción se refleje
automáticamente como entrada en otra cuenta (por ejemplo, aportaciones a
un plan de pensiones INDEXA que no emite extracto propio).
"""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from app.db import cursor
from app.services.external_transfers import apply_rules as apply_external_rules

router = APIRouter()


@router.post("/reglas-transferencias/nueva")
def rule_create(
    pattern: str = Form(...),
    target_account_id: int = Form(...),
    source_account_id: str = Form(""),
    note: str = Form(""),
):
    """Crea una regla y la aplica retroactivamente."""
    src = int(source_account_id) if source_account_id.strip() else None
    with cursor() as cur:
        cur.execute(
            """INSERT OR IGNORE INTO external_transfer_rules(
                pattern, source_account_id, target_account_id, note, active
            ) VALUES (?, ?, ?, ?, 1)""",
            (pattern.strip().lower(), src, target_account_id, note.strip() or None),
        )
        # Aplica a movimientos ya existentes que coincidan
        apply_external_rules(cur)
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/reglas-transferencias/{rule_id}/borrar")
def rule_delete(rule_id: int):
    """Borra la regla y deshace los espejos que había creado.
    Los movimientos espejo tienen hash con prefijo 'mirror:'."""
    with cursor() as cur:
        # Primero, borrar los espejos creados por cualquier regla (identificados
        # por source_hint='external_rule' Y hash con prefijo mirror:). Sólo los
        # que coincidan con el patrón + destino de esta regla concreta.
        rule = cur.execute(
            "SELECT pattern, target_account_id FROM external_transfer_rules WHERE id = ?",
            (rule_id,),
        ).fetchone()
        if rule:
            pattern = rule["pattern"]
            target = rule["target_account_id"]
            # Encuentra los espejos de esta regla y desenlázalos
            mirrors = cur.execute(
                """SELECT id, transfer_id FROM transactions
                   WHERE source_hint = 'external_rule'
                     AND account_id = ?
                     AND LOWER(description) LIKE ?""",
                (target, f"%{pattern}%"),
            ).fetchall()
            for m in mirrors:
                if m["transfer_id"]:
                    cur.execute(
                        "UPDATE transactions SET transfer_id = NULL WHERE id = ?",
                        (m["transfer_id"],),
                    )
                cur.execute("DELETE FROM transactions WHERE id = ?", (m["id"],))
        cur.execute("DELETE FROM external_transfer_rules WHERE id = ?", (rule_id,))
    return RedirectResponse("/cuentas", status_code=303)


@router.post("/reglas-transferencias/{rule_id}/toggle")
def rule_toggle(rule_id: int):
    """Activa/desactiva una regla."""
    with cursor() as cur:
        cur.execute(
            "UPDATE external_transfer_rules SET active = 1 - active WHERE id = ?",
            (rule_id,),
        )
    return RedirectResponse("/cuentas", status_code=303)
