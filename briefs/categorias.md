# Categorías — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

Dos pantallas. `/categorias` es el árbol con el que se clasifica todo: categorías padre
que se despliegan en subcategorías, con renombrar, mover y borrar en línea.
`/categorias/evolucion` dibuja cómo evoluciona cada categoría padre mes a mes, que es
como se cazan las subidas escondidas en los recibos.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | **Ninguna acción en rojo** en el árbol | hay cinco «crear» y «añadir» repartidos; ninguno es *la* acción de la pantalla, y pintarlos todos de rojo sería un semáforo |
| 2026-09-09 | Los grupos dejan de ser cajas con fondo | cada padre es una fila cerrada por filete que se despliega; el `<style>` que vivía dentro de la plantilla se muda a `tnt.css` |
| 2026-09-09 | La paleta de series del gráfico pasa a tokens `--serie-1…8` | eran ocho hex en `app/routers/categories.py`: colores decididos fuera del sistema y ciegos al tema |
| 2026-09-09 | Los controles del árbol estrenan `.input-sm` y `.w-sm/.w-md/.w-lg` | eran diez `style=` con padding y anchos a mano |

## Qué NO hacer aquí

- Ni cajas con fondo para agrupar: filete y sangría bastan.
- Ni colores de serie decididos en Python: si falta un tono, se añade `--serie-N` primero.
- Ni CSS dentro de la plantilla.

## Validación (2026-09-09)

- [x] El árbol lista gasto e ingreso en dos columnas; al desplegar un padre salen sus
      subcategorías con renombrar, mover y borrar
- [x] La evolución responde y dibuja seis series con los tokens
- [x] **Cambio de tema en caliente**: las series pasan de la paleta oscura a la clara
      (`#ff4d47` → `#e10600`, `#b0b0b0` → `#7a7a7a`…)
- [x] Cero `style=`, cero `.card`, cero emoji y cero `<style>` en las dos plantillas
- [x] Los `input` sueltos del árbol llevan `aria-label`: sin él eran campos sin nombre

## Una trampa que costó una iteración

El chevron del desplegable es un `::before`, y **cuenta como ítem del flex**: con
`justify-content:space-between` dejaba el nombre de la categoría centrado en vez de
pegado a la izquierda. Se arregla con `margin-right:auto` en `.cat-name`.
