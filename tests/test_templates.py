"""
Tests de contrato de las plantillas parciales que se devuelven por HTMX.

El caso que motiva este fichero: la celda "Categoría" de la tabla de
movimientos se actualiza por *out of band swap* después de recategorizar. El
fragmento venía envuelto en un ``<template>`` para que el parser no tirase un
``<td>`` suelto, pero htmx busca los elementos OOB con ``querySelectorAll``,
que NO entra en el contenido de un ``<template>``: el swap no ocurría nunca y
la celda se quedaba con la categoría vieja hasta recargar la página.

El arreglo es apuntar a un ``<span>``, que no tiene la restricción de parseo
del ``<td>`` y por tanto no necesita envoltorio. Estos tests fijan eso.
"""
import unittest

from app.templating import templates

CAT_TREE = [
    {"id": 1, "name": "Alimentación", "children": [{"id": 2, "name": "Supermercados"}]},
]
TX = {"id": 7, "cat_id": 2, "category_label": "Alimentación", "subcategory_label": "Supermercados"}


def render(**ctx) -> str:
    return templates.get_template("_category_cell.html").render(**ctx)


class TestCategoryCellOob(unittest.TestCase):
    def test_respuesta_htmx_trae_el_oob_visible_para_htmx(self):
        """Con oob_subcat, el fragmento lleva un elemento OOB que htmx puede ver."""
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=True)
        self.assertIn('hx-swap-oob="true"', html)
        self.assertIn('id="cat-parent-7"', html)
        self.assertIn("Alimentación", html)

    def test_el_oob_no_va_envuelto_en_template(self):
        """Un <template> lo esconde de querySelectorAll y el swap no ocurre."""
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=True)
        self.assertNotIn("<template", html)

    def test_el_oob_va_sobre_un_span_no_sobre_un_td(self):
        """Un <td> suelto lo tira el parser; por eso hacía falta el envoltorio."""
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=True)
        pos = html.index('hx-swap-oob="true"')
        etiqueta = html.rindex("<", 0, pos)
        self.assertTrue(
            html[etiqueta:].startswith("<span"),
            f"el elemento OOB debería ser un <span>, y empieza por {html[etiqueta:etiqueta + 12]!r}",
        )

    def test_el_render_inicial_no_lleva_oob(self):
        """En la tabla completa duplicaría el id cat-parent-N en cada fila."""
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=False)
        self.assertNotIn("hx-swap-oob", html)
        self.assertNotIn('id="cat-parent-7"', html)

    def test_el_control_de_celda_no_lleva_estilos_en_linea(self):
        """El vocabulario visual vive en tnt.css, no en la plantilla."""
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=False)
        self.assertNotIn("style=", html)
        self.assertIn('class="cell-edit"', html)

    def test_el_select_tiene_nombre_accesible(self):
        html = render(tx=TX, cat_tree=CAT_TREE, suggestion=None, oob_subcat=False)
        self.assertIn("aria-label=", html)


class TestMemoCell(unittest.TestCase):
    def test_sin_estilos_en_linea_y_con_nombre_accesible(self):
        html = templates.get_template("_memo_cell.html").render(tx={"id": 7, "memo": "hola"})
        self.assertNotIn("style=", html)
        self.assertIn('class="cell-edit"', html)
        self.assertIn("aria-label=", html)


if __name__ == "__main__":
    unittest.main()
