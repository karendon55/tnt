"""
Histórico de HomeBank → TNT, sin tocar la base real hasta el último paso.

    .venv/bin/python scripts/homebank_historico.py preparar [--rehacer]
    .venv/bin/python scripts/homebank_historico.py verificar
    .venv/bin/python scripts/homebank_historico.py migrar

preparar   Copia la base real en la de prueba, fotografía lo que la carga da
           por hecho y carga el ejercicio en la prueba. La real solo se lee.
verificar  Compara la real con la prueba mes a mes, desde el año siguiente al
           cargado hasta hoy, y avisa de las reglas aprendidas que cambiarían.
migrar     Copia de seguridad de la real y paso de lo revisado. Antes de
           confirmar comprueba que la real queda igual que la prueba; si no,
           no escribe nada.

Todo sale de data/importacion-homebank-2025/config.json (con --config, de
otro), que no va a git: lleva rutas, cuentas e importes reales.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.importers import homebank_xhb, indexa_valores  # noqa: E402
from app.services import homebank_historico as hh  # noqa: E402
from app.services import homebank_migracion as hm  # noqa: E402
from app.services.homebank_verificacion import Informe, comparar, reglas_que_cambiarian  # noqa: E402
from app.utils.formatters import eur  # noqa: E402

CONFIG = RAIZ / "data" / "importacion-homebank-2025" / "config.json"


# ── Bases ──────────────────────────────────────────────────────────────────

def _ruta(texto: str) -> Path:
    return (RAIZ / texto).resolve()  # las relativas, desde la raíz del proyecto


def _abrir(ruta: Path, solo_lectura: bool = False) -> sqlite3.Connection:
    destino = f"file:{ruta}?mode=ro" if solo_lectura else str(ruta)
    con = sqlite3.connect(destino, uri=solo_lectura, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def _transaccion(con: sqlite3.Connection):
    """Pide la escritura desde el principio: si la app está escribiendo en ese
    momento, espera en vez de cruzarse con ella."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con.cursor()
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def _copiar(origen: Path, destino: Path) -> None:
    """Copia íntegra con la API de backup de SQLite: incluye lo que aún esté
    en el -wal aunque la app esté abierta."""
    o, d = _abrir(origen, solo_lectura=True), sqlite3.connect(destino)
    try:
        o.backup(d)
    finally:
        d.close()
        o.close()


def _borrar(ruta: Path) -> None:
    for sufijo in ("", "-wal", "-shm"):
        Path(f"{ruta}{sufijo}").unlink(missing_ok=True)


def _prueba(cfg: dict) -> Path:
    ruta = _ruta(cfg["prueba"])
    if not ruta.exists():
        sys.exit("No hay base de prueba todavía: el primer paso es «preparar».")
    return ruta


# ── Lo que se imprime ──────────────────────────────────────────────────────

def _dec(valor) -> Decimal:
    return Decimal(repr(round(float(valor or 0), 2))).quantize(Decimal("0.01"))


def _f(iso: str) -> str:
    return f"{date.fromisoformat(iso):%d/%m/%Y}"


def _nombres(cur: sqlite3.Cursor) -> dict[int, str]:
    return {r["id"]: r["name"] for r in cur.execute("SELECT id, name FROM accounts")}


def _imprimir(informe: Informe, nombre: dict[int, str]) -> None:
    if informe.identico:
        print("  Todo igual: saldo de cada cuenta al cierre de cada mes, patrimonio, "
              "ingresos, gastos y categorías.")
        return
    for d in informe.saldos:
        print(f"  Saldo de {nombre.get(d.cuenta, d.cuenta)} el {_f(d.fecha)}: {eur(d.antes)} → {eur(d.despues)}")
    for d in informe.patrimonio:
        print(f"  Patrimonio el {_f(d.fecha)}: {eur(d.antes)} → {eur(d.despues)}")
    for k in informe.kpis:
        print(f"  {k.que.capitalize()} de {k.mes}: {eur(k.antes)} → {eur(k.despues)}")
    for c in informe.categorias_nuevas:
        print(f"  Categoría nueva: {c}")
    for c in informe.categorias_perdidas:
        print(f"  Categoría que falta: {c}")


# ── preparar ───────────────────────────────────────────────────────────────

def _plan(cur: sqlite3.Cursor, cfg: dict) -> tuple[hh.Plan, list[indexa_valores.DiaIndexa]]:
    def cat(texto: str) -> int | None:
        return hh.categoria_por_ruta(cur, texto)

    v = cfg["valoraciones"]
    cierres = indexa_valores.cierres_de_mes(indexa_valores.leer(_ruta(v["indexa"])),
                                            date.fromisoformat(v["desde"]), date.fromisoformat(v["hasta"]))
    plan = hh.Plan(
        anio=cfg["anio"],
        cuentas={int(hb): tnt for hb, tnt in cfg["cuentas"].items()},
        equivalencias=hh.leer_equivalencias(cur, _ruta(cfg["equivalencias"])),
        discrepancia_gasto=cat(cfg["discrepancia"]["gasto"]),
        discrepancia_ingreso=cat(cfg["discrepancia"]["ingreso"]),
        ajustes=tuple(hh.Ajuste(a["cuenta_hb"], date.fromisoformat(a["fecha"]), Decimal(a["importe"]),
                                cat(a["destino"]), a["traspaso"], a.get("descripcion"))
                      for a in cfg["ajustes"]),
        correcciones=tuple(hh.Correccion(c["id"], date.fromisoformat(c["fecha"]), Decimal(c["importe"]),
                                         c["cuenta_destino"], cat(c["destino"])) for c in cfg["correcciones"]),
        saldos_iniciales={int(c): Decimal(s) for c, s in cfg["saldos_iniciales"].items()},
        valoraciones=tuple((v["cuenta"], d.fecha, d.valor) for d in cierres))
    return plan, cierres


def _informe_carga(cur, plan: hh.Plan, resumen: hh.Resumen, cierres, cuenta_valorada: int) -> None:
    nombre = _nombres(cur)
    print(f"Ejercicio {plan.anio} cargado en la base de prueba.\n\nMovimientos por cuenta:")
    for cuenta, n in resumen.por_cuenta.items():
        print(f"  {nombre[cuenta]:<52} {n:>5}")
    print(f"\nParejas de traspaso: {resumen.emparejados}")
    if resumen.sin_pareja:
        print(f"Marcados como traspaso en HomeBank pero sin pareja ({len(resumen.sin_pareja)}); "
              "cuentan como gasto o ingreso:")
        for op in resumen.sin_pareja:
            print(f"  {op.fecha:%d/%m/%Y} {eur(op.importe):>14}  {nombre[plan.cuentas[op.cuenta]]}: {op.descripcion}")
    for cuenta, dif in resumen.discrepancias.items():
        print(f"\nDiscrepancia en {nombre[cuenta]}: {eur(dif)} el 31/12/{plan.anio}, "
              f"anotada como «{hh.NOTA_DISCREPANCIA}».")
    print("\nSaldos iniciales (antes → después):")
    for cuenta, (antes, despues) in resumen.saldos_iniciales.items():
        print(f"  {nombre[cuenta]:<52} {eur(antes):>14} → {eur(despues):>14}")
    if cierres:
        ultimo = cierres[-1]
        aportado = _dec(cur.execute(
            "SELECT a.initial_balance + COALESCE((SELECT SUM(t.amount) FROM transactions t "
            "WHERE t.account_id = a.id AND t.date <= ?), 0) FROM accounts a WHERE a.id = ?",
            (ultimo.fecha.isoformat(), cuenta_valorada)).fetchone()[0])
        print(f"\n{nombre[cuenta_valorada]}: {len(cierres)} valoraciones de cierre de mes. Aportado a "
              f"{ultimo.fecha:%d/%m/%Y}: {eur(ultimo.aportado)} según la entidad, {eur(aportado)} en TNT "
              f"({'cuadra' if aportado == ultimo.aportado else 'NO CUADRA'}).")


def preparar(cfg: dict, rehacer: bool) -> None:
    real, prueba = _ruta(cfg["real"]), _ruta(cfg["prueba"])
    if prueba.exists() and not rehacer:
        sys.exit(f"Ya hay una base de prueba en {prueba}.\n"
                 "Con --rehacer se tira y se prepara de nuevo: se pierde lo revisado en ella.")
    libro = homebank_xhb.leer(cfg["homebank"])
    _borrar(prueba)
    prueba.parent.mkdir(parents=True, exist_ok=True)
    _copiar(real, prueba)
    con = _abrir(prueba)
    try:
        with _transaccion(con) as cur:
            plan, cierres = _plan(cur, cfg)
            hm.guardar_foto(cur, plan)
            resumen = hh.cargar(cur, libro, plan)
            _informe_carga(cur, plan, resumen, cierres, cfg["valoraciones"]["cuenta"])
    except BaseException:
        con.close()
        _borrar(prueba)  # una prueba a medias no sirve: mejor que no exista
        raise
    con.close()
    print(f"\nBase de prueba lista: {prueba}")


# ── verificar ──────────────────────────────────────────────────────────────

def verificar(cfg: dict) -> None:
    real, prueba = _abrir(_ruta(cfg["real"]), solo_lectura=True), _abrir(_prueba(cfg), solo_lectura=True)
    desde, hasta = date(cfg["anio"] + 1, 1, 1), date.today()
    print(f"Base real frente a la de prueba, mes a mes, del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}:")
    _imprimir(comparar(real.cursor(), prueba.cursor(), desde, hasta), _nombres(real.cursor()))
    nuevas, revocadas = reglas_que_cambiarian(real, prueba)
    print(f"\nReglas aprendidas que cambiarían en la próxima importación: {len(nuevas)} nuevas (+), "
          f"{len(revocadas)} que dejarían de existir (−).")
    for patron, ruta in nuevas:
        print(f"  + «{patron}» → {ruta}")
    for patron, ruta in revocadas:
        print(f"  − «{patron}» → {ruta}")


# ── migrar ─────────────────────────────────────────────────────────────────

def migrar(cfg: dict) -> None:
    anio, real_ruta, prueba_ruta = cfg["anio"], _ruta(cfg["real"]), _prueba(cfg)
    copia = prueba_ruta.parent / f"tnt-real-antes-de-migrar-{datetime.now():%Y%m%d-%H%M%S}.db"
    _copiar(real_ruta, copia)
    print(f"Copia de seguridad de la base real: {copia}")
    prueba = _abrir(prueba_ruta, solo_lectura=True)
    hasta = date.fromisoformat(prueba.execute("SELECT MAX(date) FROM transactions").fetchone()[0])
    real = _abrir(real_ruta)
    with _transaccion(real) as cur:
        resumen = hm.migrar(prueba.cursor(), cur, anio)
        # Lo que se ve en la real antes de confirmar: tiene que ser la prueba.
        informe = comparar(prueba.cursor(), cur, date(anio, 1, 1), hasta)
        if not informe.identico:
            print("La base real no quedaría igual que la de prueba:")
            _imprimir(informe, _nombres(cur))
            raise SystemExit("No se ha migrado nada.")
    nombre = _nombres(real.cursor())
    print(f"Migrado: {resumen.movimientos} movimientos, {resumen.parejas} parejas de traspaso, "
          f"{resumen.corregidos} movimientos corregidos, {resumen.valoraciones} valoraciones.")
    for cuenta, (antes, despues) in resumen.saldos_iniciales.items():
        print(f"  Saldo inicial de {nombre[cuenta]}: {eur(antes)} → {eur(despues)}")
    print(f"Comprobado antes de confirmar: del 01/01/{anio} al {hasta:%d/%m/%Y} la base real es igual "
          "que la de prueba.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Histórico de HomeBank → TNT, pasando por una base de prueba.")
    p.add_argument("paso", choices=("preparar", "verificar", "migrar"))
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--rehacer", action="store_true",
                   help="preparar: tira la base de prueba que haya y empieza de nuevo")
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as fh:
        cfg = json.load(fh)
    try:
        if args.paso == "preparar":
            preparar(cfg, args.rehacer)
        elif args.paso == "verificar":
            verificar(cfg)
        else:
            migrar(cfg)
    except ValueError as e:
        sys.exit(f"\n{e}\nLa base real no se ha tocado.")


if __name__ == "__main__":
    main()
