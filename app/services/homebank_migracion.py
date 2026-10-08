"""
Paso del histórico de HomeBank, ya revisado, de la base de prueba a la real.

La carga (homebank_historico.py) se hace en una copia de la base real. El
usuario la revisa allí, puede recategorizar o corregir textos, y cuando da el
visto bueno esto pasa a la real exactamente lo que la carga añadió o corrigió:

- los movimientos con el prefijo del ejercicio, tal como queden en la prueba,
  con sus parejas de traspaso;
- de los movimientos que ya estaban y la carga corrigió, su categoría y pareja;
- los saldos iniciales de las cuentas cargadas;
- las valoraciones de esas cuentas hasta el cierre del ejercicio.

Nada más: lo que se toque en la prueba fuera de eso (reglas, ajustes,
movimientos de este año) se queda en la prueba.

La carga da por hechas cosas de la base real: el saldo inicial de cada cuenta,
que no tiene movimientos de ese año, cómo estaban los movimientos que corrige.
Al preparar la prueba se guarda una foto de todo eso (`guardar_foto`), y si la
real ha cambiado en algo de ello no se migra: hay que volver a prepararla. Lo
que entre después, como importar el mes siguiente, no toca la foto.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.services.homebank_historico import Plan

# El id lo pone la real; la pareja se traduce a los ids nuevos; y no van en un
# lote de importación (ver homebank_historico.py).
_SIN_COPIAR = ("id", "transfer_id", "import_batch_id")


@dataclass
class ResumenMigracion:
    movimientos: int
    parejas: int
    corregidos: int
    saldos_iniciales: dict[int, tuple[Decimal, Decimal]]  # cuenta → (antes, después)
    valoraciones: int


def _dec(valor: float | None) -> Decimal:
    return Decimal(repr(round(float(valor or 0), 2))).quantize(Decimal("0.01"))


def _clave(anio: int) -> str:
    return f"homebank:{anio}:foto"


def _foto(cur: sqlite3.Cursor, anio: int, cuentas: Iterable[int], corregidos: Iterable[int]) -> dict:
    """Lo que la carga da por hecho de una base, en tipos de JSON para poder
    guardarlo y compararlo tal cual."""
    fin = f"{anio}-12-31"

    def cuenta(c: int) -> dict:
        fila = cur.execute("SELECT initial_balance FROM accounts WHERE id = ?", (c,)).fetchone()
        return {"inicial": None if fila is None else str(_dec(fila[0])),
                "movimientos": [r[0] for r in cur.execute(
                    "SELECT id FROM transactions WHERE account_id = ? AND date <= ? ORDER BY id", (c, fin))],
                "valoraciones": [[r[0], str(_dec(r[1]))] for r in cur.execute(
                    "SELECT date, value FROM account_valuations WHERE account_id = ? AND date <= ? "
                    "ORDER BY date", (c, fin))]}

    def corregido(i: int) -> list | None:
        f = cur.execute("SELECT account_id, date, amount, category_id, transfer_id FROM transactions "
                        "WHERE id = ?", (i,)).fetchone()
        return None if f is None else [f[0], f[1], str(_dec(f[2])), f[3], f[4]]

    return {"anio": anio,
            "cuentas": {str(c): cuenta(c) for c in sorted(set(cuentas))},
            "corregidos": {str(i): corregido(i) for i in sorted(set(corregidos))}}


def guardar_foto(cur: sqlite3.Cursor, plan: Plan) -> None:
    """Fotografía la base antes de cargar el plan y guarda la foto en ella
    misma. Se llama sobre la prueba recién copiada, que aún es la real."""
    foto = _foto(cur, plan.anio, plan.cuentas.values(), [c.id_tnt for c in plan.correcciones])
    cur.execute("INSERT INTO settings(key, value) VALUES (?, ?)", (_clave(plan.anio), json.dumps(foto)))


def _ruta(cur: sqlite3.Cursor, categoria: int) -> str | None:
    f = cur.execute("SELECT c.name, p.name FROM categories c LEFT JOIN categories p ON p.id = c.parent_id "
                    "WHERE c.id = ?", (categoria,)).fetchone()
    return None if f is None else (f"{f[1]} › {f[0]}" if f[1] else f[0])


def _que_cambio(real: sqlite3.Cursor, guardada: dict, actual: dict) -> list[str]:
    cambios = []
    for c, datos in guardada["cuentas"].items():
        if actual["cuentas"].get(c) != datos:
            fila = real.execute("SELECT name FROM accounts WHERE id = ?", (int(c),)).fetchone()
            cambios.append(f"la cuenta «{fila[0] if fila else c}»")
    cambios += [f"el movimiento {i}" for i, datos in guardada["corregidos"].items()
                if actual["corregidos"].get(i) != datos]
    return cambios


def _comprobar(prueba: sqlite3.Cursor, real: sqlite3.Cursor, filas: list, arreglos: dict, cuentas: list[int]):
    """Lo que dejaría la real a medias o distinta de la prueba, antes de escribir."""
    validas = {f["id"] for f in filas} | set(arreglos)
    for f in filas:
        donde = f"«{f['description']}» del {date.fromisoformat(f['date']):%d/%m/%Y}"
        if f["account_id"] not in cuentas:
            raise ValueError(f"{donde} está en una cuenta que la carga no tocó.")
        if f["transfer_id"] is not None and f["transfer_id"] not in validas:
            raise ValueError(f"{donde} está emparejado con un movimiento que la carga no corrige.")
    for i, f in arreglos.items():
        if f["transfer_id"] is not None and f["transfer_id"] not in validas:
            raise ValueError(f"El movimiento {i} está emparejado con uno que la carga no corrige.")
    for categoria in sorted({f["category_id"] for f in [*filas, *arreglos.values()]} - {None}):
        ruta = _ruta(prueba, categoria)
        if _ruta(real, categoria) != ruta:
            raise ValueError(f"La categoría «{ruta}» no está igual en la base real.")


def migrar(prueba: sqlite3.Cursor, real: sqlite3.Cursor, anio: int) -> ResumenMigracion:
    """Pasa a `real` lo que la carga dejó en `prueba`. Va dentro de la
    transacción de quien llama: si algo falla a medias, no queda nada."""
    prefijo = f"homebank:{anio}:"
    fila = prueba.execute("SELECT value FROM settings WHERE key = ?", (_clave(anio),)).fetchone()
    if fila is None:
        raise ValueError("La base de prueba no tiene la foto de la real: no se preparó con el programa "
                         "del histórico.")
    guardada = json.loads(fila[0])
    if real.execute("SELECT 1 FROM transactions WHERE hash LIKE ? LIMIT 1", (prefijo + "%",)).fetchone():
        raise ValueError(f"El ejercicio {anio} ya está en la base real.")
    cuentas = [int(c) for c in guardada["cuentas"]]
    corregidos = [int(i) for i in guardada["corregidos"]]
    cambios = _que_cambio(real, guardada, _foto(real, anio, cuentas, corregidos))
    if cambios:
        raise ValueError("La base real ha cambiado desde que se preparó la prueba ("
                         + ", ".join(cambios) + "): hay que volver a prepararla.")

    filas = prueba.execute("SELECT * FROM transactions WHERE hash LIKE ? ORDER BY id",
                           (prefijo + "%",)).fetchall()
    arreglos = {}
    for i in corregidos:
        arreglo = prueba.execute("SELECT category_id, transfer_id FROM transactions WHERE id = ?", (i,)).fetchone()
        if arreglo is None:
            raise ValueError(f"El movimiento {i} ya no está en la base de prueba.")
        arreglos[i] = arreglo
    _comprobar(prueba, real, filas, arreglos, cuentas)

    nuevos: dict[int, int] = {}  # id en la prueba → id en la real
    if filas:
        columnas = [c for c in filas[0].keys() if c not in _SIN_COPIAR]
        sql = f"INSERT INTO transactions({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})"
        for f in filas:
            nuevos[f["id"]] = real.execute(sql, [f[c] for c in columnas]).lastrowid
    # Los corregidos conservan su id: estaban en la real antes de copiarla.
    enlaces = [(f["id"], f["transfer_id"]) for f in filas] + [(i, a["transfer_id"]) for i, a in arreglos.items()]
    for propio, pareja in enlaces:
        if pareja is not None:
            real.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?",
                         (nuevos.get(pareja, pareja), nuevos.get(propio, propio)))
    for i, a in arreglos.items():
        real.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (a["category_id"], i))
        if a["transfer_id"] is None:
            real.execute("UPDATE transactions SET transfer_id = NULL WHERE id = ?", (i,))

    iniciales: dict[int, tuple[Decimal, Decimal]] = {}
    for c in cuentas:
        en_prueba = prueba.execute("SELECT initial_balance FROM accounts WHERE id = ?", (c,)).fetchone()
        if en_prueba is None:
            raise ValueError(f"La cuenta {c} ya no está en la base de prueba.")
        antes = _dec(real.execute("SELECT initial_balance FROM accounts WHERE id = ?", (c,)).fetchone()[0])
        iniciales[c] = (antes, _dec(en_prueba[0]))
        real.execute("UPDATE accounts SET initial_balance = ? WHERE id = ?", (float(iniciales[c][1]), c))

    valoraciones = 0
    for c in cuentas:
        for v in prueba.execute("SELECT date, value, note FROM account_valuations WHERE account_id = ? "
                                "AND date <= ? ORDER BY date", (c, f"{anio}-12-31")).fetchall():
            hay = real.execute("SELECT value FROM account_valuations WHERE account_id = ? AND date = ?",
                               (c, v["date"])).fetchone()
            if hay is None:
                real.execute("INSERT INTO account_valuations(account_id, date, value, note) VALUES (?, ?, ?, ?)",
                             (c, v["date"], v["value"], v["note"]))
                valoraciones += 1
            elif _dec(hay[0]) != _dec(v["value"]):
                raise ValueError(f"La valoración del {date.fromisoformat(v['date']):%d/%m/%Y} no coincide "
                                 "con la de la base real.")
    parejas = len({frozenset(e) for e in enlaces if e[1] is not None})
    return ResumenMigracion(len(filas), parejas, len(arreglos), iniciales, valoraciones)
