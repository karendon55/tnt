"""
Lo que comparten los tests de la carga del histórico de HomeBank: un libro de
HomeBank inventado y una base de TNT con 2026 ya dentro y cuadrado.

La base es temporal, pero `unittest discover` comparte proceso: cada test
limpia al entrar y al salir.
"""
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

_TMP = tempfile.mkdtemp(prefix="tnt-homebank-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "homebank.db")

from app.db import cursor, init_db  # noqa: E402
from app.importers import homebank_xhb  # noqa: E402
from app.services import homebank_historico as hh  # noqa: E402
from app.services.categories import resolve_category  # noqa: E402
from app.services.categorizer import seed_builtin_rules  # noqa: E402

init_db()
D = Decimal


def ope(fecha, importe, cuenta, **attrs):
    extra = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f'<ope date="{fecha.toordinal()}" amount="{importe}" account="{cuenta}" {extra}/>'


# Banco A abre 2025 en 1.000 − 5 = 995,00 y lo cierra en 995 + 1.295 = 2.290,00
# en HomeBank; el banco de verdad (TNT) dice 2.281,85: −8,15 de discrepancia.
# Banco B cierra en 500 + 100 − 250 = 350,00, igual que TNT.
XHB = f"""<?xml version="1.0"?>
<homebank v="1.3999999999999999" d="050502">
<account key="1" flags="0" type="1" name="Banco A" initial="1000"/>
<account key="2" flags="0" type="1" name="Banco B" initial="500"/>
<account key="3" flags="0" type="7" name="Fondo" initial="50000"/>
<cat key="1" flags="2" name="Nómina"/>
<cat key="2" flags="0" name="Comida"/>
<cat key="3" flags="0" name="Ahorro"/>
<cat key="4" flags="2" name="Intereses"/>
{ope(date(2024, 12, 30), "-5", 1, category="2", wording="De 2024")}
{ope(date(2025, 1, 2), "1500", 1, category="1", wording="NOMINA")}
{ope(date(2025, 2, 3), "-30", 1, category="2", wording="Pago en RESTAURANTE SOL", tags="Cena con amigos")}
{ope(date(2025, 2, 4), "-20", 1, category="2", wording="Pago en MERCADO")}
{ope(date(2025, 2, 5), "-15", 1, category="2", wording="BIZUM ENVIADO")}
{ope(date(2025, 3, 1), "-100", 1, category="3", wording="Traspaso a B")}
{ope(date(2025, 3, 2), "100", 2, category="3", wording="Traspaso de A")}
{ope(date(2025, 3, 11), "-250", 2, wording="Comisiones fondo")}
{ope(date(2025, 3, 12), "250", 3, wording="Comisiones fondo")}
{ope(date(2025, 4, 1), "-50", 1, category="3", wording="Sin pareja")}
{ope(date(2025, 5, 1), "10", 1, category="4")}
{ope(date(2025, 6, 1), "-99", 1, category="2", wording="Anulado", st="4")}
{ope(date(2026, 1, 3), "-7", 1, category="2", wording="De 2026")}
</homebank>
"""


class BaseHistorico(unittest.TestCase):
    def setUp(self):
        fd, ruta = tempfile.mkstemp(suffix=".xhb")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(XHB)
        self.addCleanup(os.remove, ruta)
        self.libro = homebank_xhb.leer(ruta)
        with cursor() as cur:
            self._previas = {r[0] for r in cur.execute("SELECT id FROM categories")}
        self._vaciar()
        with cursor() as cur:
            seed_builtin_rules(cur)
            c = lambda h, k="expense": resolve_category(cur, h, default_kind=k)  # noqa: E731
            self.cat = {
                "nomina": c("Nómina y otras prestaciones|Nómina o Pensión", "income"),
                "super": c("Alimentación|Supermercados y alimentación"),
                "restaurante": c("Ocio y viajes|Cafeterías y restaurantes"),
                "traspaso": c("Transferencias|Traspaso entre cuentas"),
                "intereses": c("Ventajas ING|Abono de intereses", "income"),
                "otros_gastos": c("Otros gastos"),
                "otros_ingresos": c("Otros ingresos", "income"),
            }
            cur.execute("INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                        "VALUES ('RESTAURANTE', ?, 100, 'manual', 1)", (self.cat["restaurante"],))
            self.categorias_antes = cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            cuentas = (("Banco A", "bank", 2281.85), ("Banco B", "bank", 350.00),
                       ("Fondo", "investment", 50370.00))
            self.tnt = []
            for nombre, tipo, inicial in cuentas:
                cur.execute("INSERT INTO accounts(name, type, initial_balance) VALUES (?, ?, ?)",
                            (nombre, tipo, inicial))
                self.tnt.append(cur.lastrowid)
            a, b, f = self.tnt
            # 2026 ya está en TNT y cuadra con el banco.
            for cuenta, fecha, imp, desc in ((a, "2026-01-03", -7.0, "De 2026"),
                                             (b, "2026-03-24", -120.0, "Comisiones trimes")):
                cur.execute("INSERT INTO transactions(account_id, date, amount, description, hash) "
                            "VALUES (?, ?, ?, ?, ?)", (cuenta, fecha, imp, desc, f"tnt-{fecha}"))
            self.aportacion_2026 = cur.lastrowid
            cur.execute("INSERT INTO account_valuations(account_id, date, value) "
                        "VALUES (?, '2026-01-31', 51870.40)", (f,))

    def tearDown(self):
        self._vaciar()

    def _vaciar(self):
        with cursor() as cur:
            for tabla in ("account_valuations", "transactions", "accounts", "category_rules"):
                cur.execute(f"DELETE FROM {tabla}")
            previas = ",".join(str(i) for i in self._previas) or "0"
            cur.execute(f"DELETE FROM categories WHERE parent_id IS NOT NULL AND id NOT IN ({previas})")
            cur.execute(f"DELETE FROM categories WHERE id NOT IN ({previas})")

    def _plan(self, **cambios):
        a, b, f = self.tnt
        E = hh.Equivalencia
        datos = dict(
            anio=2025,
            cuentas={1: a, 2: b, 3: f},
            equivalencias={
                "Nómina": E(self.cat["nomina"], "fija"),
                "Comida": E(self.cat["super"], "movimiento", frozenset({self.cat["restaurante"]})),
                "Ahorro": E(self.cat["traspaso"], "traspaso"),
                "Intereses": E(self.cat["intereses"], "fija"),
                "(sin categoría)": E(None, "movimiento", frozenset()),
            },
            discrepancia_gasto=self.cat["otros_gastos"],
            discrepancia_ingreso=self.cat["otros_ingresos"],
            ajustes=(hh.Ajuste(2, date(2025, 3, 11), D("-250.00"), self.cat["traspaso"], True),
                     hh.Ajuste(3, date(2025, 3, 12), D("250.00"), self.cat["traspaso"], True)),
            correcciones=(hh.Correccion(self.aportacion_2026, date(2026, 3, 24), D("-120.00"),
                                        f, self.cat["traspaso"]),),
            saldos_iniciales={f: D("50000.00")},
            valoraciones=((f, date(2025, 12, 31), D("51642.18")),),
        )
        datos.update(cambios)
        return hh.Plan(**datos)

    def _cargar(self, **cambios):
        with cursor() as cur:
            return hh.cargar(cur, self.libro, self._plan(**cambios))

    @staticmethod
    def _filas(where="1=1", args=()):
        with cursor() as cur:
            return [dict(r) for r in cur.execute(
                f"SELECT * FROM transactions WHERE {where} ORDER BY date, id", args)]
