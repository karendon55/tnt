"""
Declaración de la Renta: lo que hace falta del piso alquilado, por ejercicio.

Nada se guarda a mano: cada total sale de los movimientos. Los ingresos son
los de la categoría «Alquiler»; los gastos, los de las subcategorías de
«Inmueble alquilado» (seguro de impago, seguro de la vivienda, IBI y
comunidad). Antes, el IBI del piso alquilado compartía «Pago de impuestos»
con el de la vivienda propia y con la tasa de basuras, y solo una nota escrita
a mano los distinguía; una categoría por concepto lo hace inequívoco.

Qué categoría es cada concepto se guarda en `settings` por su id, no por su
nombre: renombrarla no rompe nada, y si se borra, el informe lo dice en vez de
enseñar un cero.

Las sumas van en céntimos exactos (Decimal). En la base los importes son REAL,
y sumar coma flotante deja restos (0,10 + 0,20 = 0,30000000000000004) que un
total para Hacienda no puede arrastrar.

La lista «por revisar» busca lo que se ha quedado fuera: movimientos del
ejercicio que mencionan el piso (en la descripción o en la nota, sin tildes ni
mayúsculas) y no están en ningún concepto, más lo que cuelga de «Inmueble
alquilado» sin concepto. Las palabras a ignorar (la tasa de basuras, que se
decidió no contar) sacan movimientos de la lista; nunca tocan los totales.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from app.services.categorizer import resolve_category

CLAVE_AJUSTES = "renta"
_CENTIMO = Decimal("0.01")
_PADRE = "Inmueble alquilado"


@dataclass(frozen=True)
class Concepto:
    clave: str
    titulo: str
    es_ingreso: bool
    categoria: str     # «Padre|Hija», el nombre con que se crea si falta
    rotulo_total: str  # escrito entero: «Total IBI», que en minúsculas sería «ibi»


CONCEPTOS: tuple[Concepto, ...] = (
    Concepto("ingresos", "Ingresos por alquiler", True, "Alquiler",
             "Total ingresos por alquiler"),
    Concepto("impago", "Seguro de impago", False, f"{_PADRE}|Seguro de impago",
             "Total seguro de impago"),
    Concepto("vivienda", "Seguro de la vivienda", False, f"{_PADRE}|Seguro de la vivienda",
             "Total seguro de la vivienda"),
    Concepto("ibi", "IBI", False, f"{_PADRE}|IBI", "Total IBI"),
    Concepto("comunidad", "Comunidad", False, f"{_PADRE}|Comunidad", "Total comunidad"),
)
SEGUROS = ("impago", "vivienda")
# Las claves que se guardan: un id por concepto, más el padre de los gastos.
_CLAVES = tuple(c.clave for c in CONCEPTOS) + ("padre",)


@dataclass(frozen=True)
class Ajustes:
    categorias: dict[str, int]
    inmueble: str = ""            # cómo aparece el piso en descripciones y notas
    ignorar: tuple[str, ...] = ()  # palabras que sacan un movimiento de la revisión


@dataclass(frozen=True)
class Linea:
    id: int
    fecha: str
    descripcion: str
    nota: str
    cuenta: str
    categoria: str
    importe: Decimal  # con su signo, como viene del banco


@dataclass
class Apartado:
    concepto: Concepto
    categoria_id: int | None
    falta_categoria: bool
    lineas: list[Linea] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        """En positivo: lo cobrado si es un ingreso, lo pagado si es un gasto.
        Una devolución, que llega con el signo contrario, resta."""
        suma = sum((l.importe for l in self.lineas), Decimal(0))
        # El 0 de delante convierte un -0 en 0: «-0,00 €» confundiría.
        return Decimal(0) + (suma if self.concepto.es_ingreso else -suma)


@dataclass
class Informe:
    ejercicio: int
    apartados: dict[str, Apartado]
    por_revisar: list[Linea]
    revision_por_nombre: bool  # False si no hay nombre del piso con que buscar
    hay_movimientos: bool      # alguno en el año, sea del piso o no

    @property
    def total_seguros(self) -> Decimal:
        return sum((self.apartados[c].total for c in SEGUROS), Decimal(0))


# ── Importes y textos ──────────────────────────────────────────────────────

def centimos(importe: float) -> Decimal:
    """Un importe de la base (REAL) en céntimos exactos.

    Se parte de repr(), que da el número más corto que vuelve a ese mismo
    float: para un importe del banco es el que se escribió («75.02», no
    75.0199999999999960209606797434389591217041015625)."""
    return Decimal(repr(float(importe))).quantize(_CENTIMO, rounding=ROUND_HALF_UP)


def normalizar(texto: str | None) -> str:
    """Mayúsculas, sin tildes y con un solo espacio: «Cálle  Ejémplo» → «CALLE EJEMPLO»."""
    if not texto:
        return ""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto)
                         if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.upper().split())


def _contiene(texto: str, frase: str) -> bool:
    """La frase, ya normalizada, como palabras enteras: «TGR» no casa dentro
    de otra palabra. Con lookarounds y no \\b, para que valga también una
    frase que empieza o acaba en signo («C.P.»)."""
    return bool(frase) and re.search(
        rf"(?<!\w){re.escape(frase)}(?!\w)", texto) is not None


# ── Ajustes (en `settings`) ────────────────────────────────────────────────

def _leer(texto: str) -> dict | None:
    """Los ajustes guardados, o None si no son lo que se espera."""
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    cats, inmueble, ignorar = (datos.get("categorias"), datos.get("inmueble", ""),
                               datos.get("ignorar", []))
    if not isinstance(cats, dict) or not all(
            isinstance(k, str) and type(v) is int for k, v in cats.items()):
        return None
    if not isinstance(inmueble, str) or not isinstance(ignorar, list) \
            or not all(isinstance(p, str) for p in ignorar):
        return None
    return {"categorias": dict(cats), "inmueble": inmueble, "ignorar": tuple(ignorar)}


def _escribir(cur: sqlite3.Cursor, aj: Ajustes) -> None:
    cur.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (CLAVE_AJUSTES, json.dumps({"categorias": aj.categorias, "inmueble": aj.inmueble,
                                    "ignorar": list(aj.ignorar)}, ensure_ascii=False)),
    )


def _crear_categorias(cur: sqlite3.Cursor, claves: Iterable[str]) -> dict[str, int]:
    """Busca cada categoría por su nombre y crea la que falte.
    resolve_category no duplica: si «Inmueble alquilado › IBI» ya existe,
    devuelve esa, y «Alquiler» se reutiliza aunque la creara el usuario."""
    pedidas = set(claves)
    hechas = {c.clave: resolve_category(cur, c.categoria,
                                        default_kind="income" if c.es_ingreso else "expense")
              for c in CONCEPTOS if c.clave in pedidas}
    if "padre" in pedidas:
        hechas["padre"] = resolve_category(cur, _PADRE, default_kind="expense")
    return hechas


def cargar_ajustes(cur: sqlite3.Cursor) -> Ajustes:
    """Los ajustes del módulo. La primera vez crea sus categorías y los guarda.

    Si a los guardados les falta una clave (un concepto nuevo), se crea esa;
    lo que ya estaba no se toca aunque su categoría se haya borrado, para que
    el informe pueda avisarlo. Unos ajustes ilegibles se rehacen buscando las
    categorías por su nombre, sin duplicarlas."""
    fila = cur.execute("SELECT value FROM settings WHERE key = ?", (CLAVE_AJUSTES,)).fetchone()
    datos = _leer(fila["value"]) if fila else None
    if datos is None:
        aj = Ajustes(categorias=_crear_categorias(cur, _CLAVES))
        _escribir(cur, aj)
        return aj
    cats = datos["categorias"]
    faltan = [k for k in _CLAVES if k not in cats]
    if faltan:
        cats.update(_crear_categorias(cur, faltan))
    aj = Ajustes(cats, datos["inmueble"], datos["ignorar"])
    if faltan:
        _escribir(cur, aj)
    return aj


def guardar_ajustes(cur: sqlite3.Cursor, inmueble: str, ignorar: Iterable[str]) -> Ajustes:
    """Guarda cómo se llama el piso y qué ignorar al revisar. Quita espacios
    sobrantes, palabras vacías y repetidas (sin mirar tildes ni mayúsculas)."""
    actual = cargar_ajustes(cur)
    limpias: list[str] = []
    vistas: set[str] = set()
    for palabra in ignorar:
        palabra = " ".join((palabra or "").split())
        clave = normalizar(palabra)
        if clave and clave not in vistas:
            vistas.add(clave)
            limpias.append(palabra)
    aj = Ajustes(actual.categorias, " ".join((inmueble or "").split()), tuple(limpias))
    _escribir(cur, aj)
    return aj


def reparar_categorias(cur: sqlite3.Cursor) -> Ajustes:
    """Vuelve a crear las categorías del módulo que se hayan borrado."""
    actual = cargar_ajustes(cur)
    existentes = {r[0] for r in cur.execute("SELECT id FROM categories")}
    rotas = [k for k, v in actual.categorias.items() if v not in existentes]
    cats = dict(actual.categorias)
    cats.update(_crear_categorias(cur, rotas))
    aj = Ajustes(cats, actual.inmueble, actual.ignorar)
    _escribir(cur, aj)
    return aj


# ── Ejercicios ─────────────────────────────────────────────────────────────

def ejercicios(cur: sqlite3.Cursor, hoy: date) -> list[int]:
    """Los años con movimientos, más el actual y el anterior aunque estén
    vacíos. Del más reciente al más antiguo."""
    con_datos = {int(r[0]) for r in cur.execute(
        "SELECT DISTINCT substr(date, 1, 4) FROM transactions "
        "WHERE date GLOB '[0-9][0-9][0-9][0-9]-*'")}
    return sorted(con_datos | {hoy.year, hoy.year - 1}, reverse=True)


def ejercicio_por_defecto(hoy: date) -> int:
    """La campaña de la Renta va de abril a junio: hasta junio se prepara la
    declaración del año anterior; desde julio, la del que está en curso."""
    return hoy.year - 1 if hoy.month <= 6 else hoy.year


# ── El informe ─────────────────────────────────────────────────────────────

def informe(cur: sqlite3.Cursor, ejercicio: int, ajustes: Ajustes) -> Informe:
    """Detalle y total de cada concepto en el ejercicio, y lo que queda por revisar.

    Una sola lectura de los movimientos del año, de cualquier cuenta: las
    archivadas también, porque un alquiler cobrado en 2026 sigue siéndolo
    aunque la cuenta se cierre después. Un traspaso cuenta por su categoría:
    el alquiler llega como «Traspaso interno recibido»."""
    existentes = {r[0] for r in cur.execute("SELECT id FROM categories")}
    apartados: dict[str, Apartado] = {}
    concepto_de: dict[int, str] = {}
    for c in CONCEPTOS:
        cat_id = ajustes.categorias.get(c.clave)
        falta = cat_id is None or cat_id not in existentes
        apartados[c.clave] = Apartado(c, cat_id, falta)
        if not falta:
            concepto_de[cat_id] = c.clave

    padre = ajustes.categorias.get("padre")
    nombre = normalizar(ajustes.inmueble)
    ignorar = [normalizar(p) for p in ajustes.ignorar]
    por_revisar: list[Linea] = []
    filas = cur.execute(
        """SELECT t.id, t.date, t.amount, t.description, t.memo, a.name AS cuenta,
                  t.category_id, c.parent_id,
                  COALESCE(p.name || ' › ', '') || c.name AS categoria
           FROM transactions t
           JOIN accounts a ON a.id = t.account_id
           LEFT JOIN categories c ON c.id = t.category_id
           LEFT JOIN categories p ON p.id = c.parent_id
           WHERE t.date BETWEEN ? AND ?
           ORDER BY t.date, t.id""",
        (f"{ejercicio:04d}-01-01", f"{ejercicio:04d}-12-31"),
    ).fetchall()
    for f in filas:
        linea = Linea(f["id"], f["date"], f["description"] or "", f["memo"] or "",
                      f["cuenta"], f["categoria"] or "Sin categoría", centimos(f["amount"]))
        # La categoría del concepto o una hija suya (decisión 7).
        clave = concepto_de.get(f["category_id"]) or concepto_de.get(f["parent_id"])
        if clave:
            apartados[clave].lineas.append(linea)
            continue
        texto = normalizar(f"{linea.descripcion} {linea.nota}")
        if any(_contiene(texto, p) for p in ignorar):
            continue
        bajo_el_padre = padre is not None and padre in (f["category_id"], f["parent_id"])
        if bajo_el_padre or _contiene(texto, nombre):
            por_revisar.append(linea)
    return Informe(ejercicio, apartados, por_revisar, revision_por_nombre=bool(nombre),
                   hay_movimientos=bool(filas))
