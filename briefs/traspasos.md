# Traspasos — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

`/traspasos`, en la barra de arriba porque se revisa cada mes al importar. Un movimiento
entre cuentas propias sale de una y entra en otra: si los dos lados no van emparejados,
ensucian los ingresos y los gastos del mes. Tres bloques: lo ya emparejado, las
sugerencias automáticas y el emparejado a mano.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | El h1 pasa de "Traspasos entre cuentas" a **"Traspasos"** | la pestaña ya lo dice; el subtítulo explica por qué importa |
| 2026-09-09 | La acción roja es **Emparejar como traspaso**, la del formulario | el "Emparejar" de cada sugerencia baja a botón normal, como Restaurar o Deshacer en el resto de tablas |
| 2026-09-09 | Los mensajes de éxito y error pasan a la línea de aviso | eran tarjetas con `style="border-left: 3px solid var(--success, #2ecc71)"` y símbolos ✓ / ⚠ |
| 2026-09-09 | Los anchos de las dos tablas se van a CSS (`.table-pairs`, `.table-suggest`) | eran nueve `<col style="width:…">`; el comentario de por qué existen viaja con ellos |

## Qué NO hacer aquí

- Ni tarjetas, ni bordes de color con literales para marcar el tono.
- Ni un segundo rojo: el de las sugerencias es una acción de fila, no la principal.

## Validación (2026-09-09)

Con un par de traspaso inventado en la base de demostración:

- [x] La sugerencia aparece (importes opuestos, cuentas distintas, misma fecha)
- [x] Emparejar → «Emparejados correctamente» con el punto verde, Emparejados pasa a 1
      y la sección de sugerencias desaparece
- [x] Desemparejar → 303, vuelve a Emparejados (0) y Sugerencias (1)
- [x] 1440 y 375; las tablas scrollean dentro, la página no
- [x] Cero `style=`, cero `.card` y cero emoji

## Corrección funcional (2026-09-09)

La consulta de sugerencias filtraba por `t1.amount < 0` **y** por `t1.id < t2.id`.
Las dos condiciones servían para lo mismo —quedarse con una sola de las dos filas
que el JOIN devuelve por par— y juntas se pasaban de frenada: si la salida se
importó **después** de la entrada, el par no se sugería nunca. Es la mitad de los
casos, y falla en silencio: una sugerencia que no aparece no se echa de menos.

Basta con `t1.amount < 0`: de dos importes que suman cero, exactamente uno es
negativo. De paso, eso garantiza que la salida caiga siempre a la izquierda, que es
como lo lee la tabla («de dónde sale → a dónde entra»).

Comprobado en la base de demostración con un par montado al revés a propósito:
con el filtro viejo, 0 sugerencias; sin él, 1. En la base real del usuario no
ocultaba ninguna hoy, pero habría ocultado la próxima que llegara en ese orden.

Cubierto por `tests/test_traspasos.py` (17 tests).
