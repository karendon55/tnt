"""
Comparación de dos bases de TNT: la prueba de que cargar historia no
descuadra lo que ya había.

Para cada mes de un periodo compara el saldo de cada cuenta al cierre, el
patrimonio y los ingresos y gastos del mes, y devuelve exactamente qué cambió.
Avisa también de categorías nuevas o perdidas.

Y de algo menos visible: las reglas aprendidas. Cada importación vuelve a
aprenderlas de lo categorizado. Lo cargado del histórico no cuenta
(categorizer.PREFIJO_HISTORICO), pero lo que la carga recategoriza de lo que ya
había sí. `reglas_que_cambiarian` lo calcula sobre copias en memoria, sin
escribir nada.
"""
from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.analytics import month_income_expense
from app.services.balances import balances_by_account, total_balance
from app.services.categorizer import learn_rules_from_known


@dataclass(frozen=True)
class DifSaldo:
    fecha: str
    cuenta: int
    antes: Decimal
    despues: Decimal


@dataclass(frozen=True)
class DifPatrimonio:
    fecha: str
    antes: Decimal
    despues: Decimal


@dataclass(frozen=True)
class DifMes:
    mes: str
    que: str  # "ingresos" | "gastos"
    antes: Decimal
    despues: Decimal


@dataclass
class Informe:
    meses: list[str]
    saldos: list[DifSaldo] = field(default_factory=list)
    patrimonio: list[DifPatrimonio] = field(default_factory=list)
    kpis: list[DifMes] = field(default_factory=list)
    categorias_nuevas: list[str] = field(default_factory=list)
    categorias_perdidas: list[str] = field(default_factory=list)

    @property
    def identico(self) -> bool:
        return not (self.saldos or self.patrimonio or self.kpis
                    or self.categorias_nuevas or self.categorias_perdidas)


def _d(valor: float | None) -> Decimal:
    return Decimal(repr(round(float(valor or 0), 2))).quantize(Decimal("0.01"))


def _meses(desde: date, hasta: date) -> list[tuple[str, str, str]]:
    """(«AAAA-MM», primer día, cierre) de cada mes; el último cierra en `hasta`."""
    meses = []
    y, m = desde.year, desde.month
    while (y, m) <= (hasta.year, hasta.month):
        fin = date(y, m, calendar.monthrange(y, m)[1])
        meses.append((f"{y:04d}-{m:02d}", date(y, m, 1).isoformat(), min(fin, hasta).isoformat()))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return meses


def _categorias(cur: sqlite3.Cursor) -> set[str]:
    return {f"{p} › {n}" if p else n for n, p in cur.execute(
        "SELECT c.name, p.name FROM categories c LEFT JOIN categories p ON p.id = c.parent_id")}


def comparar(antes: sqlite3.Cursor, despues: sqlite3.Cursor, desde: date, hasta: date) -> Informe:
    meses = _meses(desde, hasta)
    informe = Informe([m for m, _, _ in meses])
    cuentas = sorted({r[0] for r in antes.execute("SELECT id FROM accounts")}
                     | {r[0] for r in despues.execute("SELECT id FROM accounts")})
    for mes, inicio, cierre in meses:
        sa, sd = balances_by_account(antes, cierre), balances_by_account(despues, cierre)
        for cuenta in cuentas:
            a, d = _d(sa.get(cuenta)), _d(sd.get(cuenta))
            if a != d:
                informe.saldos.append(DifSaldo(cierre, cuenta, a, d))
        pa, pd = _d(total_balance(antes, cierre)), _d(total_balance(despues, cierre))
        if pa != pd:
            informe.patrimonio.append(DifPatrimonio(cierre, pa, pd))
        ka, kd = month_income_expense(antes, inicio, cierre), month_income_expense(despues, inicio, cierre)
        for clave, que in (("income", "ingresos"), ("expense", "gastos")):
            if _d(ka[clave]) != _d(kd[clave]):
                informe.kpis.append(DifMes(mes, que, _d(ka[clave]), _d(kd[clave])))
    ca, cd = _categorias(antes), _categorias(despues)
    informe.categorias_nuevas, informe.categorias_perdidas = sorted(cd - ca), sorted(ca - cd)
    return informe


def _aprendidas(con: sqlite3.Connection) -> set[tuple[str, str]]:
    """Las reglas aprendidas que quedarían tras la próxima importación, sobre
    una copia en memoria: (patrón, «Padre › Hija»)."""
    if con.in_transaction:
        # SQLite no deja copiar una base a medio escribir desde su propia
        # conexión: contesta «bloqueada» y la copia reintentaría para siempre.
        raise ValueError("La base tiene cambios sin confirmar: confírmalos antes de comparar las reglas.")
    copia = sqlite3.connect(":memory:")
    try:
        con.backup(copia)
        copia.row_factory = sqlite3.Row
        learn_rules_from_known(copia.cursor())
        return {(patron, f"{p} › {n}" if p else n) for patron, n, p in copia.execute(
            """SELECT r.pattern, c.name, p.name FROM category_rules r JOIN categories c ON c.id = r.category_id
               LEFT JOIN categories p ON p.id = c.parent_id WHERE r.source = 'learned'""")}
    finally:
        copia.close()


def reglas_que_cambiarian(antes: sqlite3.Connection, despues: sqlite3.Connection):
    """(nuevas, revocadas): lo que lo cargado cambia en las reglas aprendidas.
    Se aprende en las dos bases para que no salga lo que TNT aprendería igual."""
    a, d = _aprendidas(antes), _aprendidas(despues)
    return sorted(d - a), sorted(a - d)
