"""
Unificación de «Transferencias» con el árbol de ING. Decidido por el usuario
el 8/10/2026.

TNT sembraba «Transferencias › Traspaso entre cuentas», y las importaciones de
ING traen su propio árbol: «Otros gastos › Transferencias» para el dinero que
va a otras personas y «Movimientos excluidos › Traspaso entre cuentas» para el
que va entre cuentas propias. Convivían dos de cada. Como se hizo con «Bizum
enviado», se queda el de ING:

- lo emparejado, y lo suelto que entra, va a «Movimientos excluidos ›
  Traspaso entre cuentas»;
- lo suelto que sale es dinero a otra persona (la paga mensual, «PAGO
  TRASPASOS»): va a «Otros gastos › Transferencias», con una regla manual para
  que las próximas vayan ahí;
- las reglas integradas pasan a esas dos y las manuales siguen a sus
  movimientos; las aprendidas se borran, y la próxima importación las vuelve
  a aprender de lo que ha quedado;
- se borran «Transferencias» y su «Traspaso entre cuentas».

Los ingresos y gastos no cambian: lo emparejado no cuenta y lo suelto cuenta
igual que antes. Va dentro de la transacción de quien llama.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.services.categories import resolve_category
from app.services.categorizer import seed_builtin_rules

ING_TRASPASO = "Movimientos excluidos|Traspaso entre cuentas"
ING_TRANSFERENCIAS = "Otros gastos|Transferencias"
REGLA_PAGA = "PAGO TRASPASOS"


@dataclass
class Resumen:
    traspasos: int        # a «Movimientos excluidos › Traspaso entre cuentas»
    sueltos: int          # a «Otros gastos › Transferencias»
    reglas_borradas: int  # aprendidas


def unificar(cur: sqlite3.Cursor) -> Resumen | None:
    """Unifica, o devuelve None si ya no queda «Transferencias» que unificar."""
    fila = cur.execute("SELECT id FROM categories WHERE name = 'Transferencias' AND parent_id IS NULL").fetchone()
    if fila is None:
        return None
    padre = fila[0]
    otras = [r[0] for r in cur.execute(
        "SELECT name FROM categories WHERE parent_id = ? AND name != 'Traspaso entre cuentas'", (padre,))]
    if otras:
        raise ValueError(f"«Transferencias» tiene otras subcategorías ({', '.join(otras)}): muévelas antes.")
    hija = cur.execute("SELECT id FROM categories WHERE parent_id = ? AND name = 'Traspaso entre cuentas'",
                       (padre,)).fetchone()
    viejas = [padre] + ([hija[0]] if hija else [])
    marcas = ",".join("?" * len(viejas))
    if cur.execute(f"SELECT 1 FROM budgets WHERE category_id IN ({marcas})", viejas).fetchone():
        raise ValueError("Hay un presupuesto en «Transferencias»: pásalo a otra categoría antes de unificar.")

    traspaso = resolve_category(cur, ING_TRASPASO)
    transferencias = resolve_category(cur, ING_TRANSFERENCIAS)
    sueltos = cur.execute(f"UPDATE transactions SET category_id = ? WHERE category_id IN ({marcas}) "
                          "AND transfer_id IS NULL AND amount < 0", (transferencias, *viejas)).rowcount
    traspasos = cur.execute(f"UPDATE transactions SET category_id = ? WHERE category_id IN ({marcas})",
                            (traspaso, *viejas)).rowcount

    for vieja, destino in ((viejas[-1], traspaso), (padre, transferencias)):
        # Si el destino ya tiene ese patrón, la vieja sobra y se borra abajo.
        cur.execute("UPDATE OR IGNORE category_rules SET category_id = ? WHERE category_id = ? "
                    "AND source = 'manual'", (destino, vieja))
    aprendidas = cur.execute(f"SELECT COUNT(*) FROM category_rules WHERE category_id IN ({marcas}) "
                             "AND source = 'learned'", viejas).fetchone()[0]
    cur.execute(f"DELETE FROM category_rules WHERE category_id IN ({marcas})", viejas)
    cur.execute("INSERT OR IGNORE INTO category_rules(pattern, category_id, priority, source, hits) "
                "VALUES (?, ?, 200, 'manual', 0)", (REGLA_PAGA, transferencias))
    for categoria in reversed(viejas):  # la hija antes que la madre
        cur.execute("DELETE FROM categories WHERE id = ?", (categoria,))
    seed_builtin_rules(cur)  # vuelve a poner las integradas que apuntaban a las viejas
    return Resumen(traspasos, sueltos, aprendidas)
