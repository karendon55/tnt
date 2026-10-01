"""
Router /reglas-transferencias — gestión de reglas de transferencias externas.

Las reglas permiten que un movimiento con cierta descripción se refleje
automáticamente como entrada en otra cuenta (por ejemplo, aportaciones a
un plan de pensiones INDEXA que no emite extracto propio).
"""
from __future__ import annotations

import math
from urllib.parse import urlencode

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from app.db import cursor
from app.services.external_transfers import apply_rules as apply_external_rules

router = APIRouter()

# Estas reglas viven en /reglas desde la reestructuración de menús. Antes se
# volvía a /cuentas, que es donde estaban: tras crear una regla aterrizabas en
# otra pantalla sin saber si había funcionado.
_VOLVER = "/reglas"


def _volver(*, msg: str = "", err: str = "") -> RedirectResponse:
    qs = urlencode({k: v for k, v in (("msg", msg), ("err", err)) if v})
    return RedirectResponse(f"{_VOLVER}?{qs}" if qs else _VOLVER, status_code=303)


def _parse_importe(raw: str) -> tuple[float | None, str | None]:
    """(importe, error) a partir de lo que llega del formulario.

    Vacío es válido y significa «cualquier importe». Si viene, tiene que ser
    una cantidad positiva y finita; se acepta coma decimal. Se guarda en valor
    absoluto porque la misma regla casa con la apertura (negativa) y con la
    cancelación (positiva) de un depósito.
    """
    texto = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not texto:
        return None, None
    try:
        valor = float(texto)
    except ValueError:
        return None, "El importe no es un número."
    if not math.isfinite(valor) or valor <= 0:
        return None, "El importe tiene que ser una cantidad positiva."
    return round(valor, 2), None


@router.post("/reglas-transferencias/nueva")
def rule_create(
    pattern: str = Form(...),
    target_account_id: int = Form(...),
    source_account_id: str = Form(""),
    note: str = Form(""),
    amount: str = Form(""),
):
    """Crea una regla y la aplica retroactivamente."""
    patron = pattern.strip().lower()
    if not patron:
        return _volver(err="La regla necesita un texto que buscar en la descripción.")
    src = int(source_account_id) if source_account_id.strip() else None
    if src == target_account_id:
        return _volver(err="La cuenta origen y la de destino no pueden ser la misma.")
    importe, error = _parse_importe(amount)
    if error:
        return _volver(err=error)

    with cursor() as cur:
        # UNIQUE(pattern, source_account_id, target_account_id): antes era un
        # INSERT OR IGNORE y un duplicado se perdía sin avisar.
        cur.execute(
            """INSERT OR IGNORE INTO external_transfer_rules(
                pattern, source_account_id, target_account_id, amount, note, active
            ) VALUES (?, ?, ?, ?, ?, 1)""",
            (patron, src, target_account_id, importe, note.strip() or None),
        )
        if cur.rowcount == 0:
            return _volver(err="Ya hay una regla con ese texto, esa cuenta origen y "
                               "esa cuenta destino. Bórrala antes si quieres cambiarla.")
        # Aplica a movimientos ya existentes que coincidan
        creados = apply_external_rules(cur)
    return _volver(msg=f"Regla creada. Movimientos reflejados ahora: {creados}.")


@router.post("/reglas-transferencias/{rule_id}/borrar")
def rule_delete(rule_id: int):
    """Borra la regla y deshace los espejos que había creado.
    Los movimientos espejo tienen hash con prefijo 'mirror:'."""
    with cursor() as cur:
        # Primero, borrar los espejos creados por cualquier regla (identificados
        # por source_hint='external_rule' Y hash con prefijo mirror:). Sólo los
        # que coincidan con el patrón + destino de esta regla concreta.
        rule = cur.execute(
            "SELECT pattern, target_account_id, amount FROM external_transfer_rules "
            "WHERE id = ?",
            (rule_id,),
        ).fetchone()
        if rule:
            pattern = rule["pattern"]
            target = rule["target_account_id"]
            # Encuentra los espejos de esta regla y desenlázalos. Si la regla
            # tiene importe, solo los de ese importe: en la cuenta del depósito
            # anual vive también el espejo de la cancelación de 100.000 € de
            # agosto, y llevárselo la convertiría otra vez en ingreso.
            mirrors = cur.execute(
                """SELECT id, transfer_id FROM transactions
                   WHERE source_hint = 'external_rule'
                     AND account_id = ?
                     AND LOWER(description) LIKE ?
                     AND (? IS NULL OR ROUND(ABS(amount), 2) = ROUND(?, 2))""",
                (target, f"%{pattern}%", rule["amount"], rule["amount"]),
            ).fetchall()
            for m in mirrors:
                if m["transfer_id"]:
                    cur.execute(
                        "UPDATE transactions SET transfer_id = NULL WHERE id = ?",
                        (m["transfer_id"],),
                    )
                cur.execute("DELETE FROM transactions WHERE id = ?", (m["id"],))
        cur.execute("DELETE FROM external_transfer_rules WHERE id = ?", (rule_id,))
    return _volver(msg="Regla borrada.")


@router.post("/reglas-transferencias/{rule_id}/toggle")
def rule_toggle(rule_id: int):
    """Activa/desactiva una regla."""
    with cursor() as cur:
        cur.execute(
            "UPDATE external_transfer_rules SET active = 1 - active WHERE id = ?",
            (rule_id,),
        )
    return _volver()
