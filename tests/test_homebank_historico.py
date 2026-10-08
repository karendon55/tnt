"""
Tests de la carga del histórico de HomeBank en una base de TNT.

Lo que no puede fallar, porque el histórico entra detrás de datos que ya
cuadran con el banco:

- Los saldos de después (2026) no se mueven ni un céntimo: el saldo inicial
  de cada cuenta retrocede exactamente lo que se movió en el año cargado.
- No se crea ninguna categoría: cada una de HomeBank va a la de TNT que diga
  la tabla de equivalencias, y si falta alguna, no se escribe nada.
- Solo se emparejan como traspaso los movimientos marcados como tales: por
  importe a secas, dos Bizum de 15 € el mismo día serían una pareja falsa.
- Si HomeBank no cuadra con el banco a fin de año, la diferencia queda como
  un movimiento visible («Discrepancia en la importación»), no escondida.

Datos inventados. La base es temporal, pero `unittest discover` comparte
proceso: cada test limpia al entrar y al salir.
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
from app.services.analytics import balances_by_account  # noqa: E402
from app.services.categorizer import resolve_category, seed_builtin_rules  # noqa: E402

init_db()
D = Decimal


def _ope(fecha, importe, cuenta, **attrs):
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
{_ope(date(2024, 12, 30), "-5", 1, category="2", wording="De 2024")}
{_ope(date(2025, 1, 2), "1500", 1, category="1", wording="NOMINA")}
{_ope(date(2025, 2, 3), "-30", 1, category="2", wording="Pago en RESTAURANTE SOL", tags="Cena con amigos")}
{_ope(date(2025, 2, 4), "-20", 1, category="2", wording="Pago en MERCADO")}
{_ope(date(2025, 2, 5), "-15", 1, category="2", wording="BIZUM ENVIADO")}
{_ope(date(2025, 3, 1), "-100", 1, category="3", wording="Traspaso a B")}
{_ope(date(2025, 3, 2), "100", 2, category="3", wording="Traspaso de A")}
{_ope(date(2025, 3, 11), "-250", 2, wording="Comisiones fondo")}
{_ope(date(2025, 3, 12), "250", 3, wording="Comisiones fondo")}
{_ope(date(2025, 4, 1), "-50", 1, category="3", wording="Sin pareja")}
{_ope(date(2025, 5, 1), "10", 1, category="4")}
{_ope(date(2025, 6, 1), "-99", 1, category="2", wording="Anulado", st="4")}
{_ope(date(2026, 1, 3), "-7", 1, category="2", wording="De 2026")}
</homebank>
"""


class _Base(unittest.TestCase):
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


class TestCarga(_Base):
    def test_cada_movimiento_del_ejercicio_en_su_cuenta(self):
        r = self._cargar()
        a, b, f = self.tnt
        nuevas = self._filas("hash LIKE 'homebank:2025:%'")
        por_cuenta = {c: sum(1 for x in nuevas if x["account_id"] == c) for c in self.tnt}
        # A: 7 de HomeBank + la discrepancia; B: 2; fondo: el de 2025 y la corrección de 2026.
        self.assertEqual(por_cuenta, {a: 8, b: 2, f: 2})
        self.assertEqual(r.por_cuenta, {a: 7, b: 2, f: 1})
        self.assertFalse(any(x["date"] < "2025-01-01" for x in nuevas))

    def test_la_nota_y_la_categoria_de_homebank_se_conservan(self):
        self._cargar()
        cena = self._filas("description = 'Pago en RESTAURANTE SOL'")[0]
        self.assertEqual((cena["memo"], cena["source_hint"]), ("Cena con amigos", "Comida"))

    def test_sin_descripcion_toma_el_nombre_de_su_categoria(self):
        self._cargar()
        self.assertEqual(len(self._filas("description = 'Intereses' AND amount = 10")), 1)

    def test_no_se_crea_ninguna_categoria(self):
        self._cargar()
        with cursor() as cur:
            self.assertEqual(cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
                             self.categorias_antes)


class TestCategorias(_Base):
    def _categoria(self, descripcion):
        return self._filas("description = ?", (descripcion,))[0]["category_id"]

    def test_fija(self):
        self._cargar()
        self.assertEqual(self._categoria("NOMINA"), self.cat["nomina"])

    def test_segun_el_movimiento_solo_acepta_lo_permitido(self):
        self._cargar()
        self.assertEqual(self._categoria("Pago en RESTAURANTE SOL"), self.cat["restaurante"])
        self.assertEqual(self._categoria("Pago en MERCADO"), self.cat["super"])
        # La regla de Bizum diría «Bizum enviado», que aquí no se acepta.
        self.assertEqual(self._categoria("BIZUM ENVIADO"), self.cat["super"])

    def test_una_categoria_sin_equivalencia_no_escribe_nada(self):
        plan = self._plan()
        del plan.equivalencias["Ahorro"]
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "Ahorro"):
                hh.cargar(cur, self.libro, plan)
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])

    def test_leer_equivalencias_rechaza_un_destino_que_no_existe(self):
        fd, ruta = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8-sig") as fh:
            fh.write("HomeBank;Propuesta en TNT;Cómo;Acepta de las reglas\n"
                     "Comida;Alimentación › No existe;fija;\n")
        self.addCleanup(os.remove, ruta)
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "No existe"):
                hh.leer_equivalencias(cur, ruta)

    def test_categoria_por_ruta(self):
        with cursor() as cur:
            self.assertEqual(hh.categoria_por_ruta(cur, " Alimentación › Supermercados y alimentación "),
                             self.cat["super"])
            self.assertIsNone(hh.categoria_por_ruta(cur, hh.SIN_CATEGORIA))
            with self.assertRaisesRegex(ValueError, "«Inventada»"):
                hh.categoria_por_ruta(cur, "Inventada")


class TestTraspasos(_Base):
    def test_se_emparejan_los_marcados(self):
        r = self._cargar()
        ida = self._filas("description = 'Traspaso a B'")[0]
        vuelta = self._filas("description = 'Traspaso de A'")[0]
        self.assertEqual((ida["transfer_id"], vuelta["transfer_id"]), (vuelta["id"], ida["id"]))
        self.assertEqual(r.emparejados, 2 + 1)  # Ahorro, el fondo de 2025 y la corrección de 2026

    def test_el_que_no_tiene_pareja_se_avisa_y_queda_suelto(self):
        r = self._cargar()
        self.assertEqual([(o.fecha, o.importe) for o in r.sin_pareja], [(date(2025, 4, 1), D("-50.00"))])
        self.assertIsNone(self._filas("description = 'Sin pareja'")[0]["transfer_id"])

    def test_el_ajuste_empareja_el_traspaso_al_fondo(self):
        self._cargar()
        banco, fondo = sorted(self._filas("description = 'Comisiones fondo'"), key=lambda x: x["amount"])
        self.assertEqual((banco["transfer_id"], fondo["transfer_id"]), (fondo["id"], banco["id"]))
        self.assertEqual({banco["category_id"], fondo["category_id"]}, {self.cat["traspaso"]})

    def test_la_correccion_de_2026_crea_la_contrapartida_y_empareja(self):
        self._cargar()
        a, b, f = self.tnt
        original = self._filas("id = ?", (self.aportacion_2026,))[0]
        pareja = self._filas("id = ?", (original["transfer_id"],))[0]
        self.assertEqual((pareja["account_id"], pareja["amount"], pareja["date"]), (f, 120.0, "2026-03-24"))
        self.assertEqual(original["category_id"], self.cat["traspaso"])

    def test_una_correccion_que_no_coincide_no_escribe_nada(self):
        mala = hh.Correccion(self.aportacion_2026, date(2026, 3, 24), D("-999.00"), self.tnt[2],
                             self.cat["traspaso"])
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "no coincide"):
                hh.cargar(cur, self.libro, self._plan(correcciones=(mala,)))
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])


class TestTraspasosDeUnaMismaCuenta(_Base):
    def test_dos_opuestos_de_la_misma_cuenta_no_son_un_traspaso(self):
        extra = (_ope(date(2025, 7, 1), "60", 1, category="3", wording="Entra 60")
                 + _ope(date(2025, 7, 1), "-60", 1, category="3", wording="Sale 60"))
        fd, ruta = tempfile.mkstemp(suffix=".xhb")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(XHB.replace("</homebank>", extra + "\n</homebank>"))
        self.addCleanup(os.remove, ruta)
        self.libro = homebank_xhb.leer(ruta)
        r = self._cargar()
        for descripcion in ("Entra 60", "Sale 60"):
            with self.subTest(movimiento=descripcion):
                self.assertIsNone(self._filas("description = ?", (descripcion,))[0]["transfer_id"])
        self.assertEqual(sum(1 for o in r.sin_pareja if o.fecha == date(2025, 7, 1)), 2)


class TestSaldos(_Base):
    FECHAS = ("2025-12-31", "2026-01-02", "2026-01-31", "2026-06-30", "2026-12-31")

    def _saldos(self, cuentas, fechas):
        with cursor() as cur:
            return {f: {c: balances_by_account(cur, f)[c] for c in cuentas} for f in fechas}

    def test_los_saldos_del_banco_desde_el_cierre_del_ejercicio_no_cambian(self):
        bancos = self.tnt[:2]
        antes = self._saldos(bancos, self.FECHAS)
        self._cargar()
        self.assertEqual(self._saldos(bancos, self.FECHAS), antes)

    def test_el_fondo_vale_lo_mismo_desde_su_primera_valoracion_de_2026(self):
        # Antes de ella no tenía ninguna y TNT enseñaba lo aportado; ahora
        # enseña el valor real de diciembre. Eso cambia, y es lo correcto.
        fondo, fechas = self.tnt[2:], self.FECHAS[2:]
        antes = self._saldos(fondo, fechas)
        self._cargar()
        self.assertEqual(self._saldos(fondo, fechas), antes)
        self.assertEqual(self._saldos(fondo, ["2026-01-02"])["2026-01-02"][self.tnt[2]], 51642.18)

    def test_la_discrepancia_queda_a_la_vista(self):
        r = self._cargar()
        a, b, f = self.tnt
        self.assertEqual(r.discrepancias, {a: D("-8.15")})
        ajuste = self._filas("hash LIKE 'homebank:2025:discrepancia:%'")
        self.assertEqual([(x["account_id"], x["date"], x["amount"], x["category_id"], x["memo"]) for x in ajuste],
                         [(a, "2025-12-31", -8.15, self.cat["otros_gastos"], "Discrepancia en la importación")])

    def test_el_saldo_inicial_pasa_a_ser_la_apertura_del_ejercicio(self):
        r = self._cargar()
        a, b, f = self.tnt
        with cursor() as cur:
            iniciales = dict(cur.execute("SELECT id, initial_balance FROM accounts"))
        self.assertEqual(round(iniciales[a], 2), float(self.libro.saldo(1, date(2024, 12, 31))))
        self.assertEqual(round(iniciales[b], 2), float(self.libro.saldo(2, date(2024, 12, 31))))
        self.assertEqual(iniciales[f], 50000.0)  # el del fondo, fijado en el plan
        self.assertEqual(r.saldos_iniciales[a], (D("2281.85"), D("995.00")))

    def test_las_valoraciones_del_fondo(self):
        self._cargar()
        with cursor() as cur:
            fechas = [r[0] for r in cur.execute(
                "SELECT date FROM account_valuations WHERE account_id = ? ORDER BY date", (self.tnt[2],))]
        self.assertEqual(fechas, ["2025-12-31", "2026-01-31"])


class TestUnaSolaVez(_Base):
    def test_no_se_carga_dos_veces(self):
        self._cargar()
        with self.assertRaisesRegex(ValueError, "ya"):
            self._cargar()
        self.assertEqual(len(self._filas("description = 'NOMINA'")), 1)


class TestAjustes(_Base):
    """Un ajuste fija un movimiento concreto de HomeBank. Dos cuotas iguales
    el mismo día en la misma cuenta se distinguen por la descripción."""

    def _gemelos(self):
        self.libro.operaciones.extend(
            homebank_xhb.OperacionHB(900 + i, date(2025, 11, 27), D("625.00"), 1, "Comida", texto, "", False)
            for i, texto in enumerate(("Cuota octubre", "Cuota noviembre")))

    def _categoria(self, descripcion):
        return self._filas("description = ?", (descripcion,))[0]["category_id"]

    def test_dos_iguales_el_mismo_dia_se_distinguen_por_la_descripcion(self):
        self._gemelos()
        ajuste = hh.Ajuste(1, date(2025, 11, 27), D("625.00"), self.cat["otros_ingresos"], False, "Cuota octubre")
        self._cargar(ajustes=self._plan().ajustes + (ajuste,))
        self.assertEqual(self._categoria("Cuota octubre"), self.cat["otros_ingresos"])
        self.assertEqual(self._categoria("Cuota noviembre"), self.cat["super"])

    def test_sin_descripcion_el_que_casa_con_dos_no_escribe_nada(self):
        self._gemelos()
        ajuste = hh.Ajuste(1, date(2025, 11, 27), D("625.00"), self.cat["otros_ingresos"], False)
        with cursor() as cur:
            with self.assertRaisesRegex(ValueError, "casa con 2"):
                hh.cargar(cur, self.libro, self._plan(ajustes=self._plan().ajustes + (ajuste,)))
        self.assertEqual(self._filas("hash LIKE 'homebank:%'"), [])


if __name__ == "__main__":
    unittest.main()
