"""
Carga del histórico de HomeBank en una base de TNT, un ejercicio cada vez.

Se carga primero en una copia de la base (la de pruebas) y solo después se
pasa a la real (ver homebank_migracion.py). Lo que garantiza esta carga, y lo
que comprueban sus tests:

- Los saldos de después no se mueven: el saldo inicial de cada cuenta
  retrocede exactamente lo que se movió en el ejercicio cargado. Si HomeBank
  no cuadra con el banco a fin de año, la diferencia entra como un movimiento
  a la vista («Discrepancia en la importación»), no escondida en el saldo.
- No se crea ninguna categoría: cada una de HomeBank va a la de TNT que diga
  la tabla de equivalencias (revisada por el usuario), y si falta alguna, no
  se escribe nada.
- Solo se emparejan como traspaso los movimientos marcados como tales: por
  importe a secas, dos Bizum iguales el mismo día serían una pareja falsa.

Las filas nuevas llevan en `hash` el prefijo «homebank:<año>:», que es lo que
impide cargar dos veces, lo que permite copiarlas luego a la base real y lo que
las deja fuera del aprendizaje de reglas (categorizer.PREFIJO_HISTORICO). No van
en un lote de importación: «Deshacer lote» borraría los movimientos pero no
devolvería los saldos iniciales, y eso sí descuadraría lo de después.
"""
from __future__ import annotations

import csv
import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.importers.homebank_xhb import LibroHB, OperacionHB
from app.services.analytics import balances_by_account
from app.services.categorizer import PREFIJO_HISTORICO, best_rule

SIN_CATEGORIA = "(sin categoría)"
NOTA_DISCREPANCIA = "Discrepancia en la importación"
_MODOS_CSV = {"fija": "fija", "según el movimiento": "movimiento", "traspaso emparejado": "traspaso"}


@dataclass(frozen=True)
class Equivalencia:
    destino: int | None             # categoría de TNT; None = sin categoría
    modo: str                       # "fija" | "movimiento" | "traspaso"
    acepta: frozenset[int] = frozenset()  # en "movimiento": lo que pueden poner las reglas


@dataclass(frozen=True)
class Ajuste:
    """Un movimiento concreto de HomeBank que no sigue a su categoría. Tiene
    que casar con uno solo; si hay dos iguales el mismo día, la descripción
    los distingue."""
    cuenta_hb: int
    fecha: date
    importe: Decimal
    destino: int | None
    traspaso: bool
    descripcion: str | None = None


@dataclass(frozen=True)
class Correccion:
    """Un movimiento que ya está en TNT y era un traspaso a otra cuenta: se crea
    su contrapartida y se emparejan."""
    id_tnt: int
    fecha: date
    importe: Decimal
    cuenta_destino: int
    destino: int


@dataclass
class Plan:
    anio: int
    cuentas: dict[int, int]                   # cuenta de HomeBank → cuenta de TNT
    equivalencias: dict[str, Equivalencia]    # categoría de HomeBank → TNT
    discrepancia_gasto: int
    discrepancia_ingreso: int
    ajustes: tuple[Ajuste, ...] = ()
    correcciones: tuple[Correccion, ...] = ()
    saldos_iniciales: dict[int, Decimal] = field(default_factory=dict)  # fijados a mano
    valoraciones: tuple[tuple[int, date, Decimal], ...] = ()
    dias_traspaso: int = 5

    @property
    def prefijo(self) -> str:
        return f"{PREFIJO_HISTORICO}{self.anio}:"


@dataclass
class Resumen:
    por_cuenta: dict[int, int]
    emparejados: int
    sin_pareja: list[OperacionHB]
    discrepancias: dict[int, Decimal]
    saldos_iniciales: dict[int, tuple[Decimal, Decimal]]  # cuenta → (antes, después)


def _dec(valor: float | None) -> Decimal:
    return Decimal(repr(round(float(valor or 0), 2))).quantize(Decimal("0.01"))


# ── La tabla de equivalencias ──────────────────────────────────────────────

def _rutas(cur: sqlite3.Cursor) -> tuple[dict[str, int], dict[str, list[int]]]:
    """«Padre › Hija» o «Nombre» → id; y las hijas de cada padre, para «Padre › *»."""
    rutas: dict[str, int] = {}
    hijas: dict[str, list[int]] = {}
    for cid, nombre, padre in cur.execute(
            "SELECT c.id, c.name, p.name FROM categories c LEFT JOIN categories p ON p.id = c.parent_id"):
        rutas[f"{padre} › {nombre}" if padre else nombre] = cid
        if padre:
            hijas.setdefault(padre, []).append(cid)
    return rutas, hijas


def _resolver(rutas: dict[str, int], texto: str) -> int | None:
    texto = texto.strip()
    if texto in ("", SIN_CATEGORIA):
        return None
    if texto not in rutas:
        raise ValueError(f"La categoría «{texto}» no existe en TNT.")
    return rutas[texto]


def categoria_por_ruta(cur: sqlite3.Cursor, texto: str) -> int | None:
    """«Padre › Hija» o «Nombre» → id en TNT; vacío o «(sin categoría)» → None.
    Una que no existe es un error: la carga no crea categorías."""
    return _resolver(_rutas(cur)[0], texto)


def leer_equivalencias(cur: sqlite3.Cursor, ruta: str | Path) -> dict[str, Equivalencia]:
    """Lee la tabla revisada por el usuario. Un destino que no existe en TNT es
    un error: la carga no crea categorías."""
    rutas, hijas = _rutas(cur)

    def categoria(texto: str) -> int | None:
        return _resolver(rutas, texto)

    def aceptadas(texto: str) -> frozenset[int]:
        ids: set[int] = set()
        for parte in filter(None, (p.strip() for p in texto.split("|"))):
            if parte.endswith(" › *"):
                padre = parte[:-4]
                if padre not in rutas:
                    raise ValueError(f"La categoría «{padre}» no existe en TNT.")
                ids.update([rutas[padre], *hijas.get(padre, [])])
            else:
                ids.add(categoria(parte))
        return frozenset(i for i in ids if i is not None)

    tabla: dict[str, Equivalencia] = {}
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        for fila in csv.DictReader(fh, delimiter=";"):
            modo = _MODOS_CSV.get(fila["Cómo"].strip())
            if modo is None:
                raise ValueError(f"«{fila['Cómo']}» no es una forma conocida de clasificar "
                                 f"({fila['HomeBank']}).")
            tabla[fila["HomeBank"].strip()] = Equivalencia(
                categoria(fila["Propuesta en TNT"]), modo,
                aceptadas(fila.get("Acepta de las reglas") or ""))
    return tabla


# ── La carga ───────────────────────────────────────────────────────────────

def _comprobar(cur: sqlite3.Cursor, ops: list[OperacionHB], plan: Plan) -> dict[int, Ajuste]:
    """Todo lo que puede fallar, antes de escribir nada. Devuelve qué ajuste
    corresponde a cada operación (por su índice en el fichero)."""
    if cur.execute("SELECT 1 FROM transactions WHERE hash LIKE ? LIMIT 1",
                   (plan.prefijo + "%",)).fetchone():
        raise ValueError(f"El ejercicio {plan.anio} ya se cargó en esta base.")
    por_ajuste: dict[int, Ajuste] = {}
    for aj in plan.ajustes:
        casan = [o for o in ops if (o.cuenta, o.fecha, o.importe) == (aj.cuenta_hb, aj.fecha, aj.importe)
                 and aj.descripcion in (None, o.descripcion)]
        if len(casan) != 1:
            raise ValueError(f"El ajuste del {aj.fecha:%d/%m/%Y} ({aj.importe} €) casa con "
                             f"{len(casan)} movimientos de HomeBank, y tiene que casar con uno.")
        por_ajuste[casan[0].indice] = aj
    faltan = sorted({o.categoria or SIN_CATEGORIA for o in ops
                     if o.indice not in por_ajuste and (o.categoria or SIN_CATEGORIA) not in plan.equivalencias})
    if faltan:
        raise ValueError("Sin equivalencia en la tabla: " + ", ".join(faltan) + ".")
    for c in plan.correcciones:
        fila = cur.execute("SELECT date, amount FROM transactions WHERE id = ?", (c.id_tnt,)).fetchone()
        if not fila or fila["date"] != c.fecha.isoformat() or _dec(fila["amount"]) != c.importe:
            raise ValueError(f"La corrección del movimiento {c.id_tnt} no coincide con lo que hay en TNT.")
    return por_ajuste


def _clasificar(op: OperacionHB, eq: Equivalencia, reglas, descripcion: str):
    """(categoría, auto_categorized, confidence) de un movimiento."""
    if eq.modo == "movimiento":
        regla = best_rule(reglas, descripcion)
        if regla is not None and regla["category_id"] in eq.acepta:
            return regla["category_id"], 1, None
    return eq.destino, 0, (1.0 if eq.destino else None)


def _insertar(cur, cuenta, fecha, importe, descripcion, nota, categoria, auto, conf, origen, huella):
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, memo, category_id, "
        "auto_categorized, confidence, source_hint, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cuenta, fecha, float(importe), descripcion, nota or None, categoria, auto, conf, origen, huella))
    return cur.lastrowid


def _emparejar(cur, filas: list[tuple[int, OperacionHB, int]], dias: int) -> tuple[int, list[OperacionHB]]:
    """Empareja importes opuestos de cuentas distintas a pocos días; la más
    cercana en fecha y, a igualdad, la primera del fichero."""
    libres = sorted(filas, key=lambda f: (f[1].fecha, f[1].indice))
    usados: set[int] = set()
    emparejados = 0
    for i, (id_a, a, cta_a) in enumerate(libres):
        if id_a in usados:
            continue
        candidatas = [(abs((b.fecha - a.fecha).days), b.indice, id_b) for id_b, b, cta_b in libres[i + 1:]
                      if id_b not in usados and cta_b != cta_a and b.importe == -a.importe
                      and abs((b.fecha - a.fecha).days) <= dias]
        if candidatas:
            id_b = min(candidatas)[2]
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (id_b, id_a))
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (id_a, id_b))
            usados.update((id_a, id_b))
            emparejados += 1
    return emparejados, [op for id_, op, _ in libres if id_ not in usados]


def cargar(cur: sqlite3.Cursor, libro: LibroHB, plan: Plan) -> Resumen:
    """Carga el ejercicio del plan. Va dentro de la transacción de quien llama:
    si algo falla a medias, no queda nada."""
    ops = libro.del_ejercicio(plan.anio, plan.cuentas)
    por_ajuste = _comprobar(cur, ops, plan)
    fin = date(plan.anio, 12, 31)
    cierre_tnt = balances_by_account(cur, fin.isoformat())
    reglas = cur.execute("SELECT pattern, category_id, priority, hits, source FROM category_rules").fetchall()

    por_cuenta = {c: 0 for c in plan.cuentas.values()}
    traspasos: list[tuple[int, OperacionHB, int]] = []
    for op in ops:
        cuenta = plan.cuentas[op.cuenta]
        descripcion = op.descripcion or op.categoria or "Sin descripción"
        aj = por_ajuste.get(op.indice)
        if aj is not None:
            categoria, auto, conf, es_traspaso = aj.destino, 0, 1.0, aj.traspaso
        else:
            eq = plan.equivalencias[op.categoria or SIN_CATEGORIA]
            (categoria, auto, conf), es_traspaso = _clasificar(op, eq, reglas, descripcion), eq.modo == "traspaso"
        huella = plan.prefijo + hashlib.sha1(
            f"{op.cuenta}|{op.indice}|{op.fecha}|{op.importe}|{descripcion}".encode()).hexdigest()[:24]
        nuevo = _insertar(cur, cuenta, op.fecha.isoformat(), op.importe, descripcion, op.nota,
                          categoria, auto, conf, op.categoria or SIN_CATEGORIA, huella)
        por_cuenta[cuenta] += 1
        if es_traspaso:
            traspasos.append((nuevo, op, cuenta))
    emparejados, sin_pareja = _emparejar(cur, traspasos, plan.dias_traspaso)

    for c in plan.correcciones:
        original = cur.execute("SELECT description, memo FROM transactions WHERE id = ?", (c.id_tnt,)).fetchone()
        pareja = _insertar(cur, c.cuenta_destino, c.fecha.isoformat(), -c.importe, original["description"],
                           original["memo"], c.destino, 0, 1.0, "corrección", f"{plan.prefijo}correccion:{c.id_tnt}")
        cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?", (c.id_tnt, pareja))
        cur.execute("UPDATE transactions SET transfer_id = ?, category_id = ? WHERE id = ?",
                    (pareja, c.destino, c.id_tnt))
        emparejados += 1

    discrepancias: dict[int, Decimal] = {}
    for cuenta_hb, cuenta in plan.cuentas.items():
        if cuenta in plan.saldos_iniciales:
            continue  # su saldo inicial lo fija el plan, con datos de la entidad
        diferencia = _dec(cierre_tnt.get(cuenta)) - libro.saldo(cuenta_hb, fin)
        if diferencia:
            _insertar(cur, cuenta, fin.isoformat(), diferencia, "Ajuste de la importación de HomeBank",
                      NOTA_DISCREPANCIA,
                      plan.discrepancia_gasto if diferencia < 0 else plan.discrepancia_ingreso,
                      0, 1.0, "homebank", f"{plan.prefijo}discrepancia:{cuenta}")
            discrepancias[cuenta] = diferencia

    iniciales: dict[int, tuple[Decimal, Decimal]] = {}
    for cuenta in plan.cuentas.values():
        antes = _dec(cur.execute("SELECT initial_balance FROM accounts WHERE id = ?", (cuenta,)).fetchone()[0])
        nuevos = _dec(cur.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = ? AND hash LIKE ? "
            "AND date <= ?", (cuenta, plan.prefijo + "%", fin.isoformat())).fetchone()[0])
        despues = plan.saldos_iniciales.get(cuenta, antes - nuevos)
        cur.execute("UPDATE accounts SET initial_balance = ? WHERE id = ?", (float(despues), cuenta))
        iniciales[cuenta] = (antes, despues)

    for cuenta, fecha, valor in plan.valoraciones:
        hay = cur.execute("SELECT value FROM account_valuations WHERE account_id = ? AND date = ?",
                          (cuenta, fecha.isoformat())).fetchone()
        if hay is not None and _dec(hay["value"]) != valor:
            raise ValueError(f"Ya hay otra valoración el {fecha:%d/%m/%Y}: no se pisa.")
        if hay is None:
            cur.execute("INSERT INTO account_valuations(account_id, date, value, note) VALUES (?, ?, ?, ?)",
                        (cuenta, fecha.isoformat(), float(valor), "Informe mensual de la entidad"))
    return Resumen(por_cuenta, emparejados, sin_pareja, discrepancias, iniciales)
