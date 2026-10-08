"""
Lector del CSV de valores que exporta Indexa Capital («Valor_<cuenta>_<fecha>.csv»).

Una fila por día, del más reciente al más antiguo: fecha; valor en euros;
rentabilidad; base 100; rentabilidad en euros; aportaciones netas del día;
aportaciones netas acumuladas; retenciones. Los importes vienen en formato
español con el símbolo del euro («63.759,24 €»).

De aquí salen el valor del fondo al cierre de cada mes, que es lo que TNT usa
como valoración, y lo aportado en cada momento, para comprobar que cuadra con
los movimientos.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

_COLUMNAS = ("Fecha", "EN EUROS (€)", "Aportaciones netas del día (€)",
             "Aportaciones netas acumuladas (€)")


@dataclass(frozen=True)
class DiaIndexa:
    fecha: date
    valor: Decimal
    aportado: Decimal      # acumulado hasta ese día
    aportado_dia: Decimal


def _euros(texto: str) -> Decimal:
    """«1.300,55 €» → 1300.55"""
    limpio = texto.replace("€", "").replace(".", "").replace(",", ".").strip()
    return Decimal(limpio or "0").quantize(Decimal("0.01"))


def leer(ruta: str | Path) -> list[DiaIndexa]:
    """Todos los días del fichero, del más antiguo al más reciente."""
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    if not filas or any(c not in filas[0] for c in _COLUMNAS):
        raise ValueError("El fichero no es el CSV de valores de Indexa Capital.")
    return sorted((DiaIndexa(date.fromisoformat(f["Fecha"].strip()), _euros(f["EN EUROS (€)"]),
                             _euros(f["Aportaciones netas acumuladas (€)"]),
                             _euros(f["Aportaciones netas del día (€)"]))
                   for f in filas if f["Fecha"].strip()), key=lambda d: d.fecha)


def cierres_de_mes(dias: list[DiaIndexa], desde: date, hasta: date) -> list[DiaIndexa]:
    """El último día con dato de cada mes entre `desde` y `hasta`, ambos incluidos."""
    cierres: dict[tuple[int, int], DiaIndexa] = {}
    for d in dias:
        if desde <= d.fecha <= hasta:
            cierres[(d.fecha.year, d.fecha.month)] = d  # vienen ordenados: queda el último
    return [cierres[k] for k in sorted(cierres)]
