"""
Tests del lector de la base de HomeBank (.xhb).

El .xhb es un XML con las cuentas, las categorías y los movimientos. Tiene tres
rarezas que el lector tiene que resolver bien, porque de él sale el histórico
que entra en TNT y los saldos con que se comprueba que nada se descuadra:

- Las fechas son números de día (el calendario de GLib, que cuenta igual que
  date.toordinal de Python).
- Los importes vienen en coma flotante con ruido («1000.0999999999999»):
  se pasan a céntimos exactos.
- Un movimiento anulado (st="4") no existe: ni se importa ni suma al saldo.

Las notas del usuario no están en «info», sino escritas en el campo de
etiquetas («Cena con amigos»). Y un movimiento dividido en varias categorías
no se sabe importar todavía: el lector se niega antes que inventarse el reparto.

Fichero inventado, sin datos reales.
"""
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from app.importers import homebank_xhb

D = Decimal


def _xhb(operaciones: str) -> str:
    """Un .xhb mínimo con dos cuentas y tres categorías (una hija)."""
    return f"""<?xml version="1.0"?>
<homebank v="1.3999999999999999" d="050502">
<account key="1" flags="0" pos="1" type="1" curr="1" name="Cuenta A" number="ES00 0000 0000 0000 0001" initial="1000.0999999999999"/>
<account key="2" flags="114" pos="2" type="1" curr="1" name="Vieja" number="" initial="0"/>
<cat key="1" flags="2" name="Nómina"/>
<cat key="2" flags="0" name="Comida"/>
<cat key="3" flags="0" parent="2" name="Restaurantes"/>
{operaciones}
</homebank>
"""


def _ope(fecha: date, importe: str, **attrs) -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f'<ope date="{fecha.toordinal()}" amount="{importe}" account="1" {extra}/>'


ANIO = [
    _ope(date(2024, 12, 31), "-10", category="2", wording="Último de 2024"),
    _ope(date(2025, 1, 1), "1500", category="1", wording="NOMINA"),
    _ope(date(2025, 3, 3), "-20.5", category="3", wording="Bar", tags="Cena con amigos", info="ticket 7"),
    _ope(date(2025, 5, 5), "-99", category="2", wording="Anulado", st="4"),
    _ope(date(2025, 6, 1), "120.03"),
    _ope(date(2026, 1, 2), "-5", category="2", wording="De 2026"),
]


class _Base(unittest.TestCase):
    def _leer(self, operaciones):
        fd, ruta = tempfile.mkstemp(suffix=".xhb")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_xhb("\n".join(operaciones)))
        self.addCleanup(os.remove, ruta)
        return homebank_xhb.leer(ruta)


class TestCuentas(_Base):
    def test_saldo_inicial_en_centimos_exactos_y_cuentas_cerradas(self):
        libro = self._leer(ANIO)
        self.assertEqual(libro.cuentas[1].inicial, D("1000.10"))
        self.assertEqual(libro.cuentas[1].nombre, "Cuenta A")
        self.assertFalse(libro.cuentas[1].cerrada)
        self.assertTrue(libro.cuentas[2].cerrada)


class TestOperaciones(_Base):
    def test_las_del_ejercicio_sin_anuladas_y_por_fecha(self):
        ops = self._leer(ANIO).del_ejercicio(2025, {1})
        self.assertEqual([o.fecha for o in ops],
                         [date(2025, 1, 1), date(2025, 3, 3), date(2025, 6, 1)])
        self.assertEqual([o.importe for o in ops], [D("1500.00"), D("-20.50"), D("120.03")])

    def test_la_categoria_hija_lleva_la_de_su_padre(self):
        bar = self._leer(ANIO).del_ejercicio(2025, {1})[1]
        self.assertEqual(bar.categoria, "Comida:Restaurantes")

    def test_la_nota_sale_de_las_etiquetas_y_de_info(self):
        ops = self._leer(ANIO).del_ejercicio(2025, {1})
        self.assertEqual(ops[1].nota, "Cena con amigos · ticket 7")
        self.assertEqual(ops[0].nota, "")

    def test_un_movimiento_sin_descripcion_ni_categoria(self):
        suelto = self._leer(ANIO).del_ejercicio(2025, {1})[2]
        self.assertEqual((suelto.descripcion, suelto.categoria), ("", None))

    def test_solo_las_cuentas_pedidas(self):
        self.assertEqual(self._leer(ANIO).del_ejercicio(2025, {2}), [])

    def test_el_indice_identifica_cada_movimiento_en_el_fichero(self):
        # Sirve para la huella de cada movimiento importado: dos iguales el
        # mismo día (dos cafés de 1,20 €) no pueden confundirse.
        ops = self._leer(ANIO + [_ope(date(2025, 3, 3), "-20.5", category="3", wording="Bar")])
        bares = [o for o in ops.del_ejercicio(2025, {1}) if o.descripcion == "Bar"]
        self.assertEqual(len(bares), 2)
        self.assertNotEqual(bares[0].indice, bares[1].indice)


class TestSaldos(_Base):
    def test_saldo_a_una_fecha_sin_contar_lo_anulado(self):
        libro = self._leer(ANIO)
        self.assertEqual(libro.saldo(1, date(2024, 12, 31)), D("990.10"))
        self.assertEqual(libro.saldo(1, date(2025, 12, 31)), D("2589.63"))
        self.assertEqual(libro.saldo(1, date(2026, 1, 31)), D("2584.63"))


class TestLoQueNoSeSabeImportar(_Base):
    def test_un_movimiento_dividido_se_rechaza(self):
        dividido = _ope(date(2025, 2, 2), "-30", scat="2||3", samt="-10||-20", smem="a||b")
        with self.assertRaisesRegex(ValueError, "dividido"):
            self._leer(ANIO + [dividido])

    def test_una_cuenta_que_no_existe_se_rechaza(self):
        huerfano = '<ope date="739000" amount="-1" account="9"/>'
        with self.assertRaisesRegex(ValueError, "cuenta"):
            self._leer(ANIO + [huerfano])


if __name__ == "__main__":
    unittest.main()
