# Movimientos — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-08

## Qué es esta superficie

La mesa de trabajo (`/movimientos`, `app/templates/transactions.html`). Es donde se
filtra, se categoriza y se corrige, con 947 filas paginadas de 50 en 50. Aquí no manda una
cifra: manda poder recorrer muchas filas sin cansarse y cambiar una categoría sin pensar.

## Referencia

La propia tabla del panel, ya en producción (`briefs/panel.md`) y el boceto
`explorations/panel-papel-oscuro/index.html`. No se buscaron referencias nuevas a
propósito: la dirección está bloqueada y esta pantalla es la misma tabla, más grande. La
regla del sistema es alcanzar el patrón antes que inventar uno.

## Patrones nuevos (sirven para las nueve pantallas que faltan)

| Patrón | Clase | Para qué |
|---|---|---|
| Cabecera de página | `.pagehead` | título serif, subtítulo y acciones. Sustituye a `.page-header` |
| Barra de filtros | `.filterbar` | una fila cerrada por filete, en vez de una tarjeta |
| Control en celda | `input.cell-edit` / `select.cell-edit` | callado hasta el hover; al foco, borde de acento y anillo |
| Botón de icono | `.icon-btn`, `.icon-btn.is-danger` | 16px, sin caja hasta el hover, con `aria-label` obligatorio |
| Paginación | `.pager` | enlaces sobre un filete, no botones |
| Rejillas de formulario | `.form-2`, `.form-1-2` | las de los diálogos, que vivían en `style=` |

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-08 | La acción roja de la pantalla es **Filtrar**, no Importar | filtrar es lo que se hace aquí; Importar lleva a otra página, así que va como enlace |
| 2026-09-08 | Los controles de categoría y memo se callan hasta que los tocas | veinte cajas de formulario por pantalla convertían la tabla en un formulario |
| 2026-09-08 | Los iconos de acción pasan de `✎` y `🗑` a SVG en línea | el emoji está prohibido, y `title` no es un nombre accesible en condiciones |
| 2026-09-08 | Los anchos del `<colgroup>` se van a CSS | eran siete `style=` en la plantilla; el comentario de por qué existen viaja con ellos |

## Validación (2026-09-08)

- [x] 1440 y 375 en navegador real; la tabla sigue con su scroll propio, la página no
- [x] Tema claro y tema oscuro
- [x] Cero `style=` y cero emoji en `transactions.html`, `_category_cell.html` y `_memo_cell.html`
- [x] Botones de solo icono con `aria-label` que nombra fecha y descripción del movimiento
- [x] Estado vacío con copy que dice qué hacer
- [x] 88 tests en verde

### Comportamiento (2026-09-08, sobre la base de demostración)

Probado contra `data/tnt-demo.db` con `./run.sh --demo`, sin tocar un solo euro real:

- [x] Categorizar: el `select` guarda por htmx y la celda hermana "Categoría" se actualiza
- [x] Sugerencia de regla tras categorizar, y "Crear regla" la crea y recategoriza en bloque
- [x] Memo: escribir y salir del campo guarda
- [x] Filtrar: `q=Gasolinera` devuelve 59 de 489, paginados de 50 en 50
- [x] Paginación: adelante y atrás, con la URL limpia
- [x] Diálogo de nuevo movimiento: abre, crea con categoría y memo, y cerrado no se ve
- [x] Borrar: confirma y borra
- [x] La base real quedó en 947 movimientos, intacta, durante toda la prueba

## Qué NO hacer aquí

- Ni una segunda acción en rojo: Filtrar es la única.
- Ni cajas de formulario visibles en reposo dentro de la tabla.
- Ni botones de solo icono sin `aria-label`.

## Pendiente

- ~~La fecha en ISO~~ **resuelto el 2026-09-09**: filtro `| fecha` → `31/08/2026`, que
  además es el formato que ya pedían los propios filtros de la pantalla.
- Hay descripciones con mojibake en la base (`Demary FruterÃ­a`), de alguna importación
  antigua. Es dato, no diseño.
