"""
Tests de cuándo casa una regla de categoría con una descripción.

Casaban por subcadena, y una regla corta se metía dentro de cualquier palabra:
la manual «IBI» (Impuestos) casaba con «transferencia recIBIda», «nómina
recIBIda» o «traspaso recIBIdo», y como lo manual gana siempre, cualquiera de
esos que llegara sin categoría del banco acababa en Impuestos. Igual con las
aprendidas: «TRANSFER» dentro de «TRANSFERENCIA», «PREST» (de
«PREST.DESEMPLEO») dentro de «PRESTAMO».

Ahora casan por palabra entera, que es como se aprenden: `extract_tokens` saca
palabras enteras. Estos tests fijan los casos del fallo; los bordes (principio
y final del texto, números y signos que cortan la palabra, tildes y Ñ que no,
un patrón que aparece dentro de una palabra y después suelto); que siguen
casando los patrones con espacios o signos y el que el banco deja cortado; y
que los cuatro sitios que casan reglas responden igual: categorizar al
importar, la regla recién creada, la sugerencia al recategorizar y
`best_rule`, con la que elige la carga del histórico de HomeBank.

Datos inventados. La base es temporal, pero `unittest discover` comparte
proceso con otros ficheros: cada test que la usa limpia al entrar y al salir.
"""
import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

# La ruta de la base se lee al importar app.config, así que se fija antes.
_TMP = tempfile.mkdtemp(prefix="tnt-reglas-palabra-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "reglas.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import cursor, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.categorizer import (  # noqa: E402
    apply_rule_retroactively, apply_rules_to_uncategorized,
)
from app.services.rule_matching import best_rule, pattern_matches  # noqa: E402

init_db()
client = TestClient(app, base_url="http://127.0.0.1:8000")


class TestPalabraEntera(unittest.TestCase):
    """`pattern_matches` a secas: el texto llega ya en mayúsculas."""

    def _todos(self, esperado, casos):
        for patron, texto in casos:
            with self.subTest(patron=patron, texto=texto):
                self.assertIs(pattern_matches(patron, texto), esperado)

    def test_no_casa_dentro_de_otra_palabra(self):
        self._todos(False, (
            ("IBI", "TRANSFERENCIA RECIBIDA"),
            ("IBI", "NOMINA RECIBIDA"),
            ("IBI", "TRASPASO INTERNO RECIBIDO"),
            ("IBI", "BIZUM RECIBIDO"),
            ("IBI", "HOTEL IBIS CENTRO"),  # tampoco como comienzo de otra
            ("TRANSFER", "TRANSFERENCIA EMITIDA"),
            ("PREST", "CUOTA PRESTAMO COCHE"),
        ))

    def test_casa_la_palabra_suelta(self):
        self._todos(True, (
            ("IBI", "RECIBO IBI 2025 AYUNTAMIENTO"),
            ("TRANSFER", "TRANSFER A CUENTA PROPIA"),
            ("PREST", "PREST.DESEMPLEO ABRIL"),
        ))

    def test_al_principio_y_al_final_del_texto(self):
        self._todos(True, (("IBI", "IBI"), ("IBI", "IBI URBANO"), ("IBI", "PAGO DEL IBI")))

    def test_numeros_y_signos_cortan_la_palabra(self):
        self._todos(True, (
            ("IBI", "RECIBO IBI2025"),
            ("IBI", "IBI-URBANA SEGUNDO PLAZO"),
            ("IBI", "PAGO (IBI)"),
            ("LIDL", "LIDL0123 CENTRO"),
            ("UBER", "UBER*TRIP AYUDA"),
            ("FERRETERIA", "1234FERRETERIA"),
        ))

    def test_las_tildes_y_la_enie_son_letras(self):
        # Un borde comprobado con [A-Z] tomaría la Ó o la Ñ por separador.
        self._todos(False, (
            ("ACCI", "ACCIÓN SOLIDARIA"),
            ("LAMO", "VIVEROS ÁLAMO"),
            ("ESPA", "TIENDA ESPAÑA"),
        ))
        self.assertTrue(pattern_matches("ACCIÓN", "ACCIÓN SOLIDARIA"))

    def test_sigue_buscando_tras_una_aparicion_dentro_de_otra_palabra(self):
        self.assertTrue(pattern_matches("IBI", "RECIBIDO IBI"))
        self.assertTrue(pattern_matches("ANA", "BANANA ANA"))  # apariciones que se solapan
        self.assertFalse(pattern_matches("ANA", "BANANA"))

    def test_patrones_con_espacios_y_signos(self):
        self._todos(True, (
            ("BIZUM RECIBIDO", "BIZUM RECIBIDO DE UN AMIGO"),
            ("PREST. DESEMPLEO", "PREST. DESEMPLEO"),
            ("REINT.CAJERO", "REINT.CAJERO 1234 CENTRO"),
            ("REPSOL WAYLET", "PAGO EN REPSOL WAYLET ES"),
        ))
        # Las dos puntas del patrón también tienen que ser palabra entera.
        self._todos(False, (
            ("BIZUM RECIBIDO", "BIZUM RECIBIDOS"),
            ("REPSOL WAYLET", "XREPSOL WAYLET"),
        ))

    def test_el_patron_que_el_banco_deja_cortado(self):
        """El banco corta las descripciones largas y deja media palabra al final.
        Una regla copiada de ahí casa porque el texto acaba donde acaba ella."""
        self._todos(True, (
            ("MUTUA ROBLE ESPAN", "MUTUA ROBLE ESPAN"),
            ("MUTUA ROBLE ESPAN", "RECIBO MUTUA ROBLE ESPAN"),
        ))
        # Si un día llega entera ya no casa: es palabra entera, no prefijo.
        # Decidido así el 2026-10-08 (docs/QUESTIONS.md).
        self.assertFalse(pattern_matches("MUTUA ROBLE ESPAN", "MUTUA ROBLE ESPANA SA"))

    def test_un_patron_vacio_no_casa_con_nada(self):
        # Por subcadena, "" casaba con todos los movimientos.
        for patron in ("", "   "):
            with self.subTest(patron=patron):
                self.assertFalse(pattern_matches(patron, "PAGO   EN   EFECTIVO"))


class TestBestRule(unittest.TestCase):
    """La regla que gana, con reglas como las devuelve la base."""

    IMPUESTOS, NOMINA, DESEMPLEO, REGALOS = 1, 2, 3, 4

    @staticmethod
    def _regla(patron, categoria, source, priority):
        return {"pattern": patron, "category_id": categoria, "source": source,
                "priority": priority, "hits": 1}

    def setUp(self):
        self.reglas = [
            self._regla("IBI", self.IMPUESTOS, "manual", 200),  # lo manual gana siempre
            self._regla("NOMINA", self.NOMINA, "builtin", 200),
            self._regla("PREST", self.DESEMPLEO, "learned", 100),
            self._regla("TRANSFER", self.REGALOS, "learned", 100),
        ]

    def _categoria(self, descripcion):
        regla = best_rule(self.reglas, descripcion)
        return regla["category_id"] if regla else None

    def test_la_nomina_recibida_no_va_a_impuestos(self):
        # Por subcadena, «IBI» casaba dentro de «RECIBIDA» y, al ser manual,
        # ganaba a «NOMINA».
        self.assertEqual(self._categoria("NOMINA RECIBIDA EMPRESA EJEMPLO"), self.NOMINA)

    def test_lo_que_solo_casaba_dentro_de_una_palabra_se_queda_sin_regla(self):
        for descripcion in ("TRANSFERENCIA RECIBIDA DE UN AMIGO", "CUOTA PRESTAMO COCHE",
                            "TRANSFERENCIA EMITIDA ALQUILER"):
            with self.subTest(descripcion=descripcion):
                self.assertIsNone(self._categoria(descripcion))

    def test_la_palabra_suelta_sigue_casando(self):
        self.assertEqual(self._categoria("RECIBO IBI 2025"), self.IMPUESTOS)
        self.assertEqual(self._categoria("PREST.DESEMPLEO ABRIL"), self.DESEMPLEO)
        self.assertEqual(self._categoria("TRANSFER A CUENTA PROPIA"), self.REGALOS)

    def test_pasa_la_descripcion_a_mayusculas(self):
        self.assertEqual(self._categoria("Recibo ibi 2025"), self.IMPUESTOS)
        self.assertIsNone(self._categoria("Transferencia recibida"))
        self.assertIsNone(self._categoria(None))


class _ConBase(unittest.TestCase):
    CATEGORIAS = ("Impuestos", "Nómina", "Desempleo", "Regalos", "Seguros")

    def setUp(self):
        self._vaciar()
        self._n = 0
        with cursor() as cur:
            self.cuenta = cur.execute(
                "INSERT INTO accounts(name, type) VALUES ('Cuenta de prueba', 'bank')").lastrowid
            self.cat = {n: cur.execute("INSERT INTO categories(name, kind) VALUES (?, 'expense')",
                                       (n,)).lastrowid for n in self.CATEGORIAS}

    def tearDown(self):
        self._vaciar()
        with cursor() as cur:
            cur.execute("DELETE FROM accounts WHERE id = ?", (self.cuenta,))
            cur.executemany("DELETE FROM categories WHERE id = ?", [(i,) for i in self.cat.values()])

    @staticmethod
    def _vaciar():
        with cursor() as cur:
            cur.execute("DELETE FROM category_rules")
            cur.execute("DELETE FROM transactions")

    def _regla(self, patron, categoria, source="manual", priority=200):
        with cursor() as cur:
            cur.execute(
                "INSERT INTO category_rules(pattern, category_id, priority, source, hits) "
                "VALUES (?, ?, ?, ?, 1)", (patron, self.cat[categoria], priority, source))
            return cur.lastrowid

    def _mov(self, descripcion, categoria=None):
        self._n += 1
        with cursor() as cur:
            return cur.execute(
                "INSERT INTO transactions(account_id, date, amount, description, hash, category_id) "
                "VALUES (?, '2026-08-01', -10.0, ?, ?, ?)",
                (self.cuenta, descripcion, f"palabra-{self._n}",
                 self.cat[categoria] if categoria else None)).lastrowid

    @staticmethod
    def _categoria_de(tx_id):
        with cursor() as cur:
            return cur.execute("SELECT category_id FROM transactions WHERE id = ?", (tx_id,)).fetchone()[0]


class TestImportarYBestRule(_ConBase):
    """Lo que hace la importación (`apply_rules_to_uncategorized`) y lo que
    elige `best_rule` tienen que ser lo mismo, movimiento a movimiento."""

    CASOS = {
        "NOMINA RECIBIDA EMPRESA EJEMPLO": "Nómina",
        "TRANSFERENCIA RECIBIDA DE UN AMIGO": None,
        "CUOTA PRESTAMO COCHE": None,
        "TRANSFERENCIA EMITIDA ALQUILER": None,
        "RECIBO IBI 2025 AYUNTAMIENTO": "Impuestos",
        "PREST.DESEMPLEO ABRIL": "Desempleo",
        "TRANSFER A CUENTA PROPIA": "Regalos",
        "RECIBO MUTUA ROBLE ESPAN": "Seguros",
    }

    def setUp(self):
        super().setUp()
        self._regla("IBI", "Impuestos")
        self._regla("MUTUA ROBLE ESPAN", "Seguros")
        self._regla("NOMINA", "Nómina", source="builtin")
        self._regla("PREST", "Desempleo", source="learned", priority=100)
        self._regla("TRANSFER", "Regalos", source="learned", priority=100)
        self.esperado = {d: self.cat[c] if c else None for d, c in self.CASOS.items()}

    def test_al_importar(self):
        ids = {d: self._mov(d) for d in self.CASOS}
        with cursor() as cur:
            apply_rules_to_uncategorized(cur)
        self.assertEqual({d: self._categoria_de(i) for d, i in ids.items()}, self.esperado)

    def test_best_rule_elige_lo_mismo(self):
        with cursor() as cur:
            reglas = cur.execute(
                "SELECT pattern, category_id, priority, hits, source FROM category_rules").fetchall()
        elegidas = {d: best_rule(reglas, d) for d in self.CASOS}
        self.assertEqual({d: r["category_id"] if r else None for d, r in elegidas.items()},
                         self.esperado)


class TestReglaNueva(_ConBase):
    """Crear una regla la aplica a lo que no tiene categoría. Antes con
    LIKE '%IBI%': la regla nacía metiendo en Impuestos cada «RECIBIDA»."""

    def test_solo_toca_lo_que_casa_y_no_tenia_categoria(self):
        casa = self._mov("RECIBO IBI 2025")
        con_guion = self._mov("IBI-URBANA SEGUNDO PLAZO")
        nomina = self._mov("NOMINA RECIBIDA EMPRESA EJEMPLO")
        ya = self._mov("IBI PAGADO EN OFICINA", categoria="Seguros")
        with cursor() as cur:
            aplicadas = apply_rule_retroactively(cur, "IBI", self.cat["Impuestos"])
        self.assertEqual(aplicadas, 2)
        self.assertEqual(self._categoria_de(casa), self.cat["Impuestos"])
        self.assertEqual(self._categoria_de(con_guion), self.cat["Impuestos"])
        self.assertIsNone(self._categoria_de(nomina))
        self.assertEqual(self._categoria_de(ya), self.cat["Seguros"], "pisó una categoría ya puesta")

    def test_desde_la_sugerencia_de_movimientos(self):
        origen = self._mov("IBI PAGADO EN OFICINA", categoria="Impuestos")
        casa = self._mov("RECIBO IBI 2025")
        nomina = self._mov("NOMINA RECIBIDA EMPRESA EJEMPLO")
        r = client.post("/reglas/crear", data={
            "pattern": " ibi ", "category_id": self.cat["Impuestos"], "tx_id": origen})
        self.assertEqual(r.status_code, 200)
        self.assertIn("1 movimiento categorizado.", r.text)
        self.assertEqual(self._categoria_de(casa), self.cat["Impuestos"])
        self.assertIsNone(self._categoria_de(nomina))
        with cursor() as cur:
            regla = cur.execute("SELECT pattern, source, hits FROM category_rules").fetchall()
        self.assertEqual([tuple(x) for x in regla], [("IBI", "manual", 2)])

    def test_con_el_patron_vacio_avisa_y_no_crea_nada(self):
        for patron in ("", "   "):  # "" llegaba como campo que falta: un 422 en JSON
            with self.subTest(patron=patron):
                r = client.post("/reglas/crear", data={
                    "pattern": patron, "category_id": self.cat["Impuestos"]}, follow_redirects=False)
                self.assertEqual(r.status_code, 303)
                self.assertIn("patrón", parse_qs(urlsplit(r.headers["location"]).query)["err"][0])
        with cursor() as cur:
            self.assertEqual(cur.execute("SELECT COUNT(*) FROM category_rules").fetchone()[0], 0)


class TestEditarRegla(_ConBase):
    def test_un_patron_vacio_no_se_guarda_y_se_avisa(self):
        regla = self._regla("IBI", "Impuestos")
        for patron in ("", "   "):  # "" llegaba como campo que falta: un 422 en JSON
            with self.subTest(patron=patron):
                r = client.post(f"/reglas/{regla}/editar", data={
                    "pattern": patron, "category_id": self.cat["Impuestos"], "priority": 200},
                    follow_redirects=False)
                self.assertEqual(r.status_code, 303)
                destino = r.headers["location"]
                error = parse_qs(urlsplit(destino).query)["err"][0]
                self.assertIn("patrón", error)
                self.assertIn(error, client.get(destino).text, "el aviso no se ve en la pantalla")
        with cursor() as cur:
            self.assertEqual(cur.execute("SELECT pattern FROM category_rules WHERE id = ?",
                                         (regla,)).fetchone()[0], "IBI")

    def test_un_patron_con_texto_se_guarda_limpio(self):
        regla = self._regla("IBI", "Impuestos")
        r = client.post(f"/reglas/{regla}/editar", data={
            "pattern": "  ibi urbana ", "category_id": self.cat["Impuestos"], "priority": 200},
            follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/reglas"))
        with cursor() as cur:
            self.assertEqual(cur.execute("SELECT pattern FROM category_rules WHERE id = ?",
                                         (regla,)).fetchone()[0], "IBI URBANA")


class TestSugerencia(_ConBase):
    """Al recategorizar un movimiento, Movimientos propone una regla y dice con
    cuántos movimientos más casa. Contaba con LIKE, así que prometía
    movimientos que la regla, por palabra entera, luego no toca."""

    def test_cuenta_lo_mismo_que_luego_hace_la_regla(self):
        origen = self._mov("PAGO EN TRANS EXPRESS")
        for i in range(3):
            self._mov(f"TRANSPORTES GARCIA {i}")  # «TRANS» solo como comienzo de otra palabra
        self._mov("TRANS EXPRESS DEVOLUCION")
        r = client.post(f"/movimientos/{origen}/categoria",
                        data={"category_id": str(self.cat["Regalos"])})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Hay <strong>1</strong> movimiento más", r.text)
        self.assertIn('<span class="tabular">TRANS</span>', r.text)

        r = client.post("/reglas/crear", data={
            "pattern": "TRANS", "category_id": self.cat["Regalos"], "tx_id": origen})
        self.assertIn("1 movimiento categorizado.", r.text)


if __name__ == "__main__":
    unittest.main()
