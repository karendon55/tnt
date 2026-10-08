"""
Tests del lector del CSV de valores de Indexa Capital.

El fichero trae una fila por día, del más reciente al más antiguo, con los
importes en formato español y el símbolo del euro. De él salen el valor del
fondo al cierre de cada mes (las valoraciones de TNT) y lo aportado, para
comprobar que cuadra con los movimientos. Cuando el último día del mes no
tiene dato (fin de semana), vale el último día que lo tenga.

Datos inventados.
"""
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from app.importers import indexa_valores

D = Decimal
CSV = ("﻿Fecha;\"EN EUROS (€)\";\"EN PORCENTAJE (%)\";\"Evolución de la cartera (base 100)\";"
       "\"Rentabilidad (€)\";\"Aportaciones netas del día (€)\";\"Aportaciones netas acumuladas (€)\";"
       "\"Retenciones del día (€)\";\"Retenciones acumuladas (€)\"\n"
       "2025-03-03;\"1.300,55 €\";+1,00 %;101,00;\"0,55 €\";\"0,00 €\";\"1.300,00 €\";\"0,00 €\";\"0,00 €\"\n"
       "2025-02-28;\"1.300,20 €\";+1,00 %;101,00;\"0,20 €\";\"300,00 €\";\"1.300,00 €\";\"0,00 €\";\"0,00 €\"\n"
       "2025-02-27;\"1.000,10 €\";+0,01 %;100,01;\"0,10 €\";\"0,00 €\";\"1.000,00 €\";\"0,00 €\";\"0,00 €\"\n"
       "2025-01-30;\"1.000,05 €\";+0,01 %;100,01;\"0,05 €\";\"0,00 €\";\"1.000,00 €\";\"0,00 €\";\"0,00 €\"\n"
       "2025-01-02;\"1.000,00 €\";0,00 %;100,00;\"0,00 €\";\"1.000,00 €\";\"1.000,00 €\";\"0,00 €\";\"0,00 €\"\n")


class TestIndexa(unittest.TestCase):
    def setUp(self):
        fd, self.ruta = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(CSV)
        self.addCleanup(os.remove, self.ruta)

    def test_lee_cada_dia_en_orden_y_en_centimos(self):
        dias = indexa_valores.leer(self.ruta)
        self.assertEqual([d.fecha for d in dias][:2], [date(2025, 1, 2), date(2025, 1, 30)])
        self.assertEqual((dias[-1].valor, dias[-1].aportado), (D("1300.55"), D("1300.00")))
        self.assertEqual(dias[2].aportado_dia, D("0.00"))
        self.assertEqual(dias[3].aportado_dia, D("300.00"))

    def test_el_cierre_de_cada_mes_es_su_ultimo_dia_con_dato(self):
        cierres = indexa_valores.cierres_de_mes(indexa_valores.leer(self.ruta),
                                                date(2025, 1, 1), date(2025, 2, 28))
        # Enero no tiene el 31: vale el 30. Marzo queda fuera del rango.
        self.assertEqual([(c.fecha, c.valor) for c in cierres],
                         [(date(2025, 1, 30), D("1000.05")), (date(2025, 2, 28), D("1300.20"))])

    def test_un_fichero_que_no_es_de_indexa_se_rechaza(self):
        with open(self.ruta, "w", encoding="utf-8") as fh:
            fh.write("fecha;importe\n2025-01-01;3\n")
        with self.assertRaisesRegex(ValueError, "Indexa"):
            indexa_valores.leer(self.ruta)


if __name__ == "__main__":
    unittest.main()
