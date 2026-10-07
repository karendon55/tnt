# Renta · referencias (2026-10-07)

La dirección está bloqueada («papel en oscuro», `design-system.md`): esta
superficie no explora estilo, lo hereda. Las referencias son las piezas de TNT
que ya resuelven lo mismo que necesita la Renta: un resumen de cifras, un
detalle de movimientos por grupo y sus totales. Capturas con datos de la base
de demostración (inventados); la construida con datos reales se queda en local
(`our-build-*.png`, ignorada por git).

## 1. Panel — `panel-demo-2026-10-07.png`

- **Previsión para el mes siguiente**: filas `.fcrow` a dos columnas, etiqueta a
  la izquierda y cifra tabular a la derecha, separadas por punteado. Es el patrón
  de los totales de la Renta (resumen de seguros y el total de cada concepto).
- **Últimos movimientos**: tabla fija con Fecha · Descripción · columna
  secundaria · Importe, importes con signo y color del semáforo, cabeceras en
  versalita pequeña. Es el detalle de cada concepto: se generaliza a
  `.table-detalle` y la usan los dos sitios.
- **Cabecera de hoja**: título serif a la izquierda y la acción secundaria en
  `.lnk` a la derecha («Ver todos»). En la Renta: «Ver en Movimientos» y
  «Exportar CSV» de cada concepto.

## 2. Movimientos — `movimientos-demo-2026-10-07.png`

- Los filtros por categoría y fechas ya existen y la exportación CSV respeta los
  mismos: la Renta no repite listados, enlaza a esos filtros con el año puesto.

## 3. Boceto bloqueado — `../panel-papel-oscuro/index.html` (`../panel-refs/boceto-2026-09-08.png`)

- Hojas separadas por filete, sin tarjetas; titulares en Georgia a 1,25rem.
- Cifras de fila y de tabla en sans tabular: el serif es para hero y KPIs, y la
  Renta no tiene ninguno. Sus totales son filas, no titulares.

## Qué NO

- Ni tarjetas ni cajas de color para los totales: filete y punteado.
- Rojo solo en importes negativos y en el punto de aviso. No hay acción roja:
  la pantalla se consulta, y «Guardar ajustes» es secundaria.
- Nada de cifras en serif en las tablas.
