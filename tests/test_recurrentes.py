"""
Tests de la detección de recurrentes y anomalías.

Es la parte más «adivina» de TNT: agrupa movimientos por comercio, decide si se
repiten con ritmo mensual o trimestral, y avisa de duplicados y subidas de
precio. Todo heurística, y hasta ahora sin un solo test.

El caso que empuja este fichero: `detect_anomalies` preguntaba a la base, una
vez por cada recurrente encontrado, cuál era el último movimiento con esa
descripción —37 consultas en la base real—. El dato ya lo tenía en la mano, y
además la consulta miraba movimientos que la agrupación había descartado a
propósito: los que son un traspaso entre cuentas propias.
"""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tnt-recu-test-")
os.environ["TNT_DB"] = os.path.join(_TMP, "recu.db")

from app.db import cursor, init_db  # noqa: E402
from app.services import recurring  # noqa: E402
from app.services.recurring import detect_anomalies, find_recurring  # noqa: E402

init_db()
_n = [0]


def _limpiar(cur):
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM accounts")
    cur.execute("INSERT INTO accounts(name, type) VALUES ('Cuenta', 'bank')")
    return cur.lastrowid


def _mov(cur, cuenta, importe, desc, fecha, transfer=None, saldo=None):
    _n[0] += 1
    cur.execute(
        "INSERT INTO transactions(account_id, date, amount, description, hash,"
        " transfer_id, balance) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cuenta, fecha, importe, desc, f"hr{_n[0]}", transfer, saldo))
    return cur.lastrowid


MESES = ("2026-03-05", "2026-04-05", "2026-05-05", "2026-06-05",
         "2026-07-05", "2026-08-05")


class TestAgrupar(unittest.TestCase):
    def test_reconoce_un_recibo_mensual(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -49.9, "RECIBO MOVISTAR FIBRA", f)
            grupos = find_recurring(cur)
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].kind, "monthly")
        self.assertEqual(grupos[0].count, 6)
        self.assertEqual(grupos[0].median_amount, -49.9)

    def test_no_mezcla_gasto_con_ingreso(self):
        """La nómina y la compra en el mismo comercio no son el mismo grupo."""
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -20.0, "ACME COBROS", f)
                _mov(cur, cta, 20.0, "ACME COBROS", f)
            grupos = find_recurring(cur)
        self.assertEqual(len(grupos), 2)
        self.assertEqual({g.count for g in grupos}, {6})

    def test_lo_que_sale_poco_no_es_recurrente(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            _mov(cur, cta, -10.0, "TIENDA RARA", "2026-03-05")
            _mov(cur, cta, -10.0, "TIENDA RARA", "2026-04-05")
            self.assertEqual(find_recurring(cur, min_occurrences=3), [])

    def test_los_traspasos_no_cuentan(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -100.0, "TRASPASO AHORRO", f)
            # cada uno enlazado a sí mismo: basta para que cuente como traspaso
            cur.execute("UPDATE transactions SET transfer_id = id")
            self.assertEqual(find_recurring(cur), [])

    def test_el_ultimo_del_grupo_viene_con_su_id_y_su_importe(self):
        """Lo que detect_anomalies necesita, sin volver a preguntar."""
        with cursor() as cur:
            cta = _limpiar(cur)
            ids = [_mov(cur, cta, -49.9, "RECIBO MOVISTAR FIBRA", f) for f in MESES]
            ultimo = _mov(cur, cta, -61.5, "RECIBO MOVISTAR FIBRA", "2026-09-05")
            g = find_recurring(cur)[0]
        self.assertEqual(g.last_id, ultimo)
        self.assertEqual(g.last_amount, -61.5)
        self.assertEqual(g.last_date, "2026-09-05")
        self.assertNotIn(g.last_id, ids[:-1])


class TestElMinimoSoloFiltra(unittest.TestCase):
    """`min_occurrences` no cambia cómo se calcula un grupo, solo cuáles pasan.

    De eso depende que el panel pueda buscar los recurrentes UNA vez con el
    mínimo más flojo (la previsión usa 2) y que las anomalías, que quieren 3,
    se queden con los que tengan tres o más. Si algún día el mínimo entrara en
    el cálculo, este test avisa antes de que las dos pantallas empiecen a
    contar cosas distintas."""

    def _poblar(self, cur):
        cta = _limpiar(cur)
        for f in MESES:
            _mov(cur, cta, -49.9, "RECIBO MOVISTAR FIBRA", f)
        for f in MESES[:3]:
            _mov(cur, cta, -12.0, "SUSCRIPCION SPOTIFY", f)
        for f in MESES[:2]:                       # solo dos: queda fuera con 3
            _mov(cur, cta, -80.0, "SEGURO COCHE", f)
        return cta

    def test_pedir_tres_es_pedir_dos_y_quedarse_con_los_de_tres(self):
        with cursor() as cur:
            self._poblar(cur)
            con_tres = find_recurring(cur, min_occurrences=3)
            con_dos = find_recurring(cur, min_occurrences=2)
        filtrados = [g for g in con_dos if g.count >= 3]
        self.assertEqual([g.payee_key for g in con_tres], [g.payee_key for g in filtrados])
        self.assertEqual([g.avg_amount for g in con_tres], [g.avg_amount for g in filtrados])
        self.assertEqual([g.last_id for g in con_tres], [g.last_id for g in filtrados])
        self.assertLess(len(con_tres), len(con_dos), "el caso no distingue nada")


class TestSubidasDePrecio(unittest.TestCase):
    def test_avisa_de_una_subida_de_mas_del_15(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -49.9, "RECIBO MOVISTAR FIBRA", f)
            subida = _mov(cur, cta, -61.5, "RECIBO MOVISTAR FIBRA", "2026-09-05")
            avisos = [a for a in detect_anomalies(cur) if a.kind == "price_jump"]
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].transaction_ids, [subida])
        self.assertIn("61,50".replace(",", "."), avisos[0].message)

    def test_una_subida_pequena_no_molesta(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -50.0, "RECIBO LUZ ENDESA", f)
            _mov(cur, cta, -52.0, "RECIBO LUZ ENDESA", "2026-09-05")   # +4%
            avisos = [a for a in detect_anomalies(cur) if a.kind == "price_jump"]
        self.assertEqual(avisos, [])

    def test_un_traspaso_posterior_no_se_toma_por_el_ultimo_recibo(self):
        """El agrupador descarta los traspasos; el aviso tiene que descartarlos
        también, o compara la mediana del recibo contra un movimiento que no es
        de esa serie."""
        with cursor() as cur:
            cta = _limpiar(cur)
            for f in MESES:
                _mov(cur, cta, -49.9, "RECIBO MOVISTAR FIBRA", f)
            espejo = _mov(cur, cta, -900.0, "RECIBO MOVISTAR FIBRA", "2026-09-30")
            cur.execute("UPDATE transactions SET transfer_id = ? WHERE id = ?",
                        (espejo, espejo))
            avisos = [a for a in detect_anomalies(cur) if a.kind == "price_jump"]
        self.assertEqual(
            avisos, [],
            "un traspaso se coló como si fuera la última factura del recibo")


class TestDuplicados(unittest.TestCase):
    def test_dos_iguales_en_tres_dias_son_sospechosos(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            a = _mov(cur, cta, -35.0, "COMPRA ZARA", "2026-08-10")
            b = _mov(cur, cta, -35.0, "COMPRA ZARA", "2026-08-11")
            avisos = [x for x in detect_anomalies(cur) if x.kind == "duplicate"]
        self.assertEqual(len(avisos), 1)
        self.assertEqual(sorted(avisos[0].transaction_ids), sorted([a, b]))

    def test_con_saldos_distintos_son_dos_compras_de_verdad(self):
        """Dos recargas de 30 € el mismo día existen. Si el banco da saldo y es
        distinto, son dos movimientos reales."""
        with cursor() as cur:
            cta = _limpiar(cur)
            _mov(cur, cta, -30.0, "RECARGA METRO", "2026-08-10", saldo=500.0)
            _mov(cur, cta, -30.0, "RECARGA METRO", "2026-08-10", saldo=470.0)
            avisos = [x for x in detect_anomalies(cur) if x.kind == "duplicate"]
        self.assertEqual(avisos, [])

    def test_lejos_en_el_tiempo_no_es_duplicado(self):
        with cursor() as cur:
            cta = _limpiar(cur)
            _mov(cur, cta, -35.0, "COMPRA ZARA", "2026-08-01")
            _mov(cur, cta, -35.0, "COMPRA ZARA", "2026-08-20")
            avisos = [x for x in detect_anomalies(cur) if x.kind == "duplicate"]
        self.assertEqual(avisos, [])



class TestLaBusquedaDeDuplicadosVaPorIndice(unittest.TestCase):
    """Sin un índice por cuenta e importe, cada movimiento se compara con todos
    los de su cuenta y el panel crece con el cuadrado de los datos: con el
    histórico de 2025 dentro, 290 ms de los 320 de la portada. Con él, 7 ms."""

    def test_busca_por_cuenta_e_importe(self):
        with cursor() as cur:
            plan = " ".join(r[3] for r in cur.execute("EXPLAIN QUERY PLAN " + recurring.SQL_DUPLICADOS))
        self.assertRegex(plan, r"SEARCH t2 USING (COVERING )?INDEX \w+ \(account_id=\? AND amount=\?")


if __name__ == "__main__":
    unittest.main()
