"""
Lector de la base de HomeBank (.xhb), para traer su histórico a TNT.

Distinto del importador de CSV de HomeBank (homebank.py): aquel lee el
fichero de «carga» de un mes y una cuenta; este lee la base entera, con todas
las cuentas y sus saldos, que es lo que hace falta para comprobar que el
histórico cuadra con lo que ya hay en TNT.

Tres rarezas del formato, resueltas aquí:

- Las fechas son números de día del calendario de GLib, que cuenta igual que
  date.toordinal de Python: date.fromordinal los convierte.
- Los importes vienen en coma flotante con ruido («4185.7299999999996»): se
  pasan a céntimos exactos.
- Un movimiento anulado (st="4") no existe: no se lista ni suma al saldo.

Las notas del usuario están escritas en el campo de etiquetas, que HomeBank
guarda como texto libre; «info» casi no se usa. La nota que llega a TNT es la
unión de los dos.

Un movimiento dividido en varias categorías (scat/samt) se rechaza: repartirlo
exige decidir qué parte va a qué categoría de TNT, y eso no se adivina. Igual
con un movimiento que apunta a una cuenta o una categoría que no existen.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Iterable

_CENTIMO = Decimal("0.01")
_ANULADA = "4"
_CERRADA = 1 << 1  # AF_CLOSED en los flags de la cuenta


def _centimos(texto: str | None) -> Decimal:
    """«4185.7299999999996» → 4185.73: se parte del texto, no de un float."""
    return Decimal(texto or "0").quantize(_CENTIMO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CuentaHB:
    clave: int
    nombre: str
    numero: str
    inicial: Decimal
    cerrada: bool


@dataclass(frozen=True)
class OperacionHB:
    indice: int              # posición en el fichero: distingue dos iguales el mismo día
    fecha: date
    importe: Decimal
    cuenta: int
    categoria: str | None    # el nombre de HomeBank; «Padre:Hija» si es hija
    descripcion: str
    nota: str
    anulada: bool


@dataclass
class LibroHB:
    cuentas: dict[int, CuentaHB]
    operaciones: list[OperacionHB]

    def saldo(self, cuenta: int, hasta: date) -> Decimal:
        """Saldo de la cuenta al cierre de `hasta`, como lo calcula HomeBank."""
        return self.cuentas[cuenta].inicial + sum(
            (o.importe for o in self.operaciones
             if o.cuenta == cuenta and not o.anulada and o.fecha <= hasta),
            Decimal(0))

    def del_ejercicio(self, anio: int, cuentas: Iterable[int]) -> list[OperacionHB]:
        """Las operaciones vivas de esas cuentas en ese año, por fecha y, a
        igualdad, en el orden del fichero."""
        quiero = set(cuentas)
        return sorted((o for o in self.operaciones
                       if o.cuenta in quiero and not o.anulada and o.fecha.year == anio),
                      key=lambda o: (o.fecha, o.indice))


def leer(ruta: str | Path) -> LibroHB:
    """Lee el .xhb entero. Lanza ValueError si hay algo que no sabe importar."""
    raiz = ET.parse(ruta).getroot()
    cuentas: dict[int, CuentaHB] = {}
    for a in raiz.iter("account"):
        clave = int(a.get("key"))
        cuentas[clave] = CuentaHB(clave, a.get("name", ""), a.get("number", ""),
                                  _centimos(a.get("initial")),
                                  bool(int(a.get("flags", "0")) & _CERRADA))
    categorias = {int(c.get("key")): c for c in raiz.iter("cat")}

    def nombre_categoria(clave: str | None, fecha: date) -> str | None:
        if not clave:
            return None
        cat = categorias.get(int(clave))
        if cat is None:
            raise ValueError(f"El movimiento del {fecha:%d/%m/%Y} tiene una categoría "
                             f"que no existe ({clave}).")
        padre = categorias.get(int(cat.get("parent") or 0))
        return f"{padre.get('name')}:{cat.get('name')}" if padre is not None else cat.get("name")

    operaciones: list[OperacionHB] = []
    for indice, o in enumerate(raiz.iter("ope")):
        fecha = date.fromordinal(int(o.get("date")))
        if o.get("scat"):
            raise ValueError(f"El movimiento del {fecha:%d/%m/%Y} está dividido en varias "
                             "categorías, y eso no se sabe importar todavía.")
        cuenta = int(o.get("account"))
        if cuenta not in cuentas:
            raise ValueError(f"El movimiento del {fecha:%d/%m/%Y} es de una cuenta que no "
                             f"existe ({cuenta}).")
        etiquetas = " ".join((o.get("tags") or "").split())
        nota = " · ".join(t for t in (etiquetas, (o.get("info") or "").strip()) if t)
        operaciones.append(OperacionHB(
            indice, fecha, _centimos(o.get("amount")), cuenta,
            nombre_categoria(o.get("category"), fecha),
            (o.get("wording") or "").strip(), nota, o.get("st") == _ANULADA))
    return LibroHB(cuentas, operaciones)
