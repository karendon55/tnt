# Presupuestos — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

`/presupuestos`, en la barra de arriba. Un límite mensual por categoría y una barra que
se llena con lo gastado. Se mira de pasada varias veces al mes; se toca poco.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | Cada presupuesto es una fila a todo el ancho, no una tarjeta en rejilla | la barra es lo que se mira, y a todo el ancho se lee de un vistazo |
| 2026-09-09 | **El estado «pasado de límite» deja de ser un degradado** | `linear-gradient(90deg, var(--accent), var(--warning))`; el sistema descarta los degradados y pasarse es rojo, sin matices |
| 2026-09-09 | La barra se define una sola vez, en `tnt.css` | estaba dos veces con valores distintos: aquí y en un `<style>` dentro de la plantilla, que ganaba por ir después |
| 2026-09-09 | Borrar pasa a icono con `aria-label`; Actualizar se queda en texto | mismo criterio que el resto: la acción que se busca en texto, la destructiva en icono |
| 2026-09-09 | «Highway to Hell» se queda | es la casa |

## Qué NO hacer aquí

- Ni degradados, ni siquiera para «esto va mal»: para eso está `--danger`.
- Ni CSS dentro de la plantilla.
- Ni tarjetas: fila, barra y filete.

Los dos `style="width: …%"` que quedan salen del dato, no son decisiones de diseño: el
estándar los admite explícitamente.

## Validación (2026-09-09)

- [x] Los tres estados con datos reales de la demo: 236,8% en rojo, 89,3% en ámbar,
      50,0% en verde
- [x] Actualizar un límite responde 303 y el total se recalcula
- [x] 1440 y 375
- [x] Cero `.card`, cero `<style>`, cero emoji, **y ningún degradado en toda la app**

## Correcciones funcionales (2026-09-09)

**El total contaba dos veces.** Con presupuesto en una categoría madre y también
en una hija, el gasto de la hija está dentro de los dos, y el total se calculaba
sumando fila a fila. Cada fila por separado es correcta; el total no. Ahora
pregunta por los movimientos distintos que caen bajo algún presupuesto.
Comprobado en la demostración: 88,15 € y no 176,30 €.

**Un límite de 0 o negativo se guardaba tan tranquilo.** No daba error: dejaba el
porcentaje en 0, la barra vacía y el aviso mudo para siempre. Se rechaza en el
borde, y los dos formularios llevan `min="0.01"`.

Cubierto por `tests/test_presupuestos.py` (18 tests).
