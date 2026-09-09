"""
Tests del filtro de fecha.

Las tablas enseñaban la fecha en ISO (`2026-08-31`), que es como la guarda
SQLite pero no como se lee un extracto en España. El filtro la pasa a
`31/08/2026`, y aguanta lo que le echen: fechas con hora, objetos date, valores
vacíos y basura.

Regla que NO se puede romper: los `<input type="date">` siguen recibiendo ISO,
porque el navegador solo entiende ese formato ahí. Por eso el filtro se aplica
en las celdas, nunca en los value= de esos campos.
"""
import unittest
from datetime import date, datetime

from app.utils.formatters import fecha


class TestFecha(unittest.TestCase):
    def test_fecha_iso(self):
        self.assertEqual(fecha("2026-08-31"), "31/08/2026")

    def test_un_digito_se_rellena(self):
        self.assertEqual(fecha("2026-01-05"), "05/01/2026")

    def test_fecha_con_hora_lleva_la_hora_sin_segundos(self):
        self.assertEqual(fecha("2026-09-09 09:48:47"), "09/09/2026 09:48")

    def test_fecha_con_hora_en_formato_t(self):
        self.assertEqual(fecha("2026-09-09T09:48:47"), "09/09/2026 09:48")

    def test_objeto_date(self):
        self.assertEqual(fecha(date(2026, 8, 31)), "31/08/2026")

    def test_objeto_datetime(self):
        self.assertEqual(fecha(datetime(2026, 9, 9, 9, 48)), "09/09/2026 09:48")

    def test_vacio_o_none(self):
        self.assertEqual(fecha(None), "")
        self.assertEqual(fecha(""), "")

    def test_lo_que_no_es_fecha_se_devuelve_tal_cual(self):
        """Mejor enseñar el valor raro que tragárselo y dejar la celda vacía."""
        self.assertEqual(fecha("mañana"), "mañana")
        self.assertEqual(fecha("2026-13-45"), "2026-13-45")

    def test_no_toca_lo_que_ya_esta_en_formato_es(self):
        self.assertEqual(fecha("31/08/2026"), "31/08/2026")


if __name__ == "__main__":
    unittest.main()
