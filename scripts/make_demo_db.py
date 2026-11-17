"""Genera una base de datos de demostración con datos inventados.

Uso:  TNT_DB=$PWD/data/tnt-demo.db .venv/bin/python scripts_demo.py

No lee nada de la base real: el esquema lo crea la propia app (init_db) y las
filas se generan aquí. Sirve para probar el comportamiento de la interfaz
—categorizar, borrar, filtrar— sin tocar dinero de verdad.
"""
import os, random, hashlib, datetime, sys

if not os.environ.get("TNT_DB"):
    sys.exit("Define TNT_DB antes de ejecutar, o crearás la base real.")

# Para encontrar app/ al lanzarlo como `python scripts/make_demo_db.py` desde la raíz.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import DB_PATH
from app.db import init_db, cursor as db_cursor

init_db()
random.seed(20260908)

CUENTAS = [
    ("Cuenta corriente", "Banco Demo", "ES0000000000000000000001", "bank", 1200.0),
    ("Cuenta de ahorro", "Banco Demo", "ES0000000000000000000002", "bank", 8000.0),
    ("Tarjeta", "Otro Banco", "ES0000000000000000000003", "bank", 0.0),
]
GASTOS = [
    ("Supermercado Ejemplo", "Alimentación", (-90, -8)),
    ("Gasolinera Ejemplo", "Vehículo y transporte", (-70, -30)),
    ("Cafetería Ejemplo", "Ocio y viajes", (-25, -3)),
    ("Tienda Ejemplo", "Compras", (-60, -5)),
    ("Farmacia Ejemplo", "Educación y salud", (-40, -4)),
    ("Recibo de la luz", "Hogar", (-120, -45)),
    ("Recibo del agua", "Hogar", (-40, -18)),
    ("Transporte público", "Vehículo y transporte", (-30, -10)),
]
INGRESOS = [("Nómina", "Nómina y otras prestaciones", (1600, 2100)),
            ("Devolución", "Ingresos varios", (5, 60))]

with db_cursor() as cur:
    if cur.execute("select count(*) from transactions").fetchone()[0]:
        sys.exit(f"{DB_PATH} ya tiene movimientos; borra el fichero si quieres regenerarla.")

    cats = {n: i for i, n in cur.execute("select id, name from categories")}
    for nombre, banco, iban, tipo, saldo in CUENTAS:
        cur.execute("insert into accounts(name,bank,iban,type,initial_balance) values(?,?,?,?,?)",
                    (nombre, banco, iban, tipo, saldo))
    ids = [r[0] for r in cur.execute("select id from accounts")]

    hoy = datetime.date(2026, 8, 31)
    n = 0
    for dia in range(240):                       # ocho meses
        f = hoy - datetime.timedelta(days=dia)
        movs = [random.choice(GASTOS) for _ in range(random.randint(0, 4))]
        if f.day == 1:
            movs.append(INGRESOS[0])
        if random.random() < .05:
            movs.append(INGRESOS[1])
        for desc, cat, (lo, hi) in movs:
            imp = round(random.uniform(lo, hi), 2)
            cuenta = random.choice(ids)
            h = hashlib.sha256(f"{f}{desc}{imp}{cuenta}{n}".encode()).hexdigest()
            # una de cada seis se queda sin categoría, para poder probar el
            # flujo de categorizar a mano
            cid = None if n % 6 == 0 else cats.get(cat)
            cur.execute(
                "insert into transactions(account_id,date,amount,description,category_id,hash,imported_at)"
                " values(?,?,?,?,?,?,?)",
                (cuenta, f.isoformat(), imp, desc, cid, h, datetime.datetime.now().isoformat(timespec="seconds")))
            n += 1

print(f"Base de demostración lista: {DB_PATH}")
print(f"  {n} movimientos inventados, {len(CUENTAS)} cuentas, del "
      f"{(hoy - datetime.timedelta(days=239)):%d/%m/%Y} al {hoy:%d/%m/%Y}")
