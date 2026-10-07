# Renta — brief de diseño

Estado: **bloqueado** · Fecha: 2026-10-07

## Qué es esta superficie

La sección «Declaración de la Renta» de Configuración (`/renta`,
`app/routers/renta.py` → `app/templates/renta.html`, cálculo en
`app/services/renta.py`). Se abre una vez al año, en la campaña, para copiar a la
declaración lo del piso alquilado: alquileres cobrados y lo pagado en seguro de
impago, seguro de la vivienda, IBI y comunidad. Tiene que dar cada total sin
dudas y enseñar de dónde sale, movimiento a movimiento. Y avisar de lo que se
haya quedado fuera.

## Referencias

| Fuente | Dónde | Qué robamos |
|---|---|---|
| Panel · Previsión | `explorations/renta-refs/panel-demo-2026-10-07.png` | filas `.fcrow` con punteado y la de total con filete: los totales |
| Panel · Últimos movimientos | la misma captura | la tabla de solo lectura, generalizada a `.table-detalle` |
| Movimientos | `explorations/renta-refs/movimientos-demo-2026-10-07.png` | sus filtros y su CSV: la Renta enlaza ahí en vez de repetir listados |
| Boceto bloqueado | `explorations/panel-papel-oscuro/index.html` | hoja y filete, titulares en Georgia, cifras de fila en sans tabular |

Notas en `explorations/renta-refs/NOTES.md`. La captura de la construida
(`our-build-2026-10-07.png`) se queda en local: sale con datos reales.

## Tokens usados

Ninguno nuevo. `--font-display` en el título y en los de cada hoja; `--font-sans`
tabular en tablas y totales; `--border` en filetes, `--border-strong` en el
punteado; `--success` / `--danger` en los importes del detalle; el punto rojo de
aviso para el año vacío y la categoría borrada.

## Componentes

| Componente | Clase | Personalización |
|---|---|---|
| Cabecera y selector de ejercicio | `.pagehead` + `.select-month` con `.lbl` | el mismo envío al cambiar que el mes del panel |
| Resumen | `.table` dentro de `.table-scroll` | concepto y total; en `.sheet-2` junto a los seguros |
| Seguros | `.fcrow` + `.fcrow.is-total` | impago, vivienda y su suma |
| Detalle de cada concepto | `.table-detalle` (`.col-fecha`, `.col-secundaria`, `.col-importe`) | la cuenta es la columna que se oculta en el móvil |
| Total de cada concepto | `.fcrow.is-total` | rótulo escrito entero («Total IBI») |
| Por revisar | `.table-detalle`, fecha enlazada al día en Movimientos | la URL no lleva el nombre del piso |
| Avisos dentro de una hoja | `.warnline-top` sin `.warnline` | el marco de `.warnline` sumaba su filete al de la hoja |
| Ajustes | `<details>` + `.filterbar` | cerrado si ya hay nombre del piso |

## Qué NO hacer en esta superficie

- Ni tarjetas ni cajas de color para los totales: filete y punteado.
- Ninguna acción roja: la pantalla se consulta; «Guardar ajustes» es secundaria.
- Ni el nombre del piso ni importes en una URL: acaban en el historial del navegador.
- Ningún total guardado: todo sale de los movimientos.

## Validación (2026-10-07)

- [x] Comparada con las referencias: las mismas piezas que el panel
- [x] 375, 768 y 1280 en navegador real, sin scroll horizontal; a 375 la cuenta se oculta
- [x] Tema claro y oscuro
- [x] El selector cambia de ejercicio y un año vacío lo dice
- [x] Totales de 2026 iguales a los calculados a mano desde los movimientos del banco
- [x] Tests: `tests/test_renta.py` (cálculo) y `tests/test_renta_pantalla.py` (pantalla)

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-07 | Un concepto, una categoría, bajo «Inmueble alquilado» | el IBI y los seguros de los dos pisos compartían categoría y solo los distinguía una nota |
| 2026-10-07 | Las categorías se recuerdan por id en `settings` | renombrarlas no rompe nada; si se borran, se avisa en vez de enseñar un cero |
| 2026-10-07 | La comunidad entra; la tasa de basuras, no | decidido por el usuario |
| 2026-10-07 | «Por revisar» busca el nombre del piso sin tildes ni mayúsculas y salta las palabras a ignorar | los recibos nuevos del piso caen donde los ponen las reglas, y alguien tiene que verlos |
| 2026-10-07 | La tabla de solo lectura del panel pasa a ser `.table-detalle`, compartida | la Renta necesitaba la misma; copiarla eran dos sitios que mantener |
