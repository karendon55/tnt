# Panel — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-08

## Qué es esta superficie

La portada de TNT (`/`, `app/routers/dashboard.py` → `app/templates/dashboard.html`). La
ve Jesús César varias veces al mes, sobre todo después de importar el extracto. Tiene que
responder a tres preguntas sin hacer scroll: cuánto hay, cómo ha ido el mes y si algo pide
atención. Todo lo demás es detalle.

## Referencias

| Fuente | Dónde | Qué robamos |
|---|---|---|
| Boceto interno "papel en oscuro" | `explorations/panel-papel-oscuro/index.html` | la cifra hero en serif a 64px, la banda de tres KPI separada por filetes verticales, las filas de categoría con punteado, el gráfico de línea a 1,6px sin relleno |
| shadcn charts + Tremor | — | ejes tenues, una sola serie acentuada, sin sombras duras |

Capturas en `explorations/panel-refs/`. El proceso de decisión, en
`explorations/panel-direcciones/NOTES.md`.

## Tokens usados

Todos de `design-system.md` / `tnt.css`: `--font-display` (Georgia) en hero, titulares de
sección y KPIs; `--font-sans` con `tabular-nums` en tablas y categorías; `--border` para
los filetes, `--border-strong` para el punteado; `--accent` solo en marca, acción principal
y punto de aviso; `--success` / `--danger` en importes.

## Componentes

| Componente | Clase | Personalización |
|---|---|---|
| Hero del patrimonio | `.hero` + `.lbl` + `.hero-value` | sin tarjeta, sin degradado; `<h1>` es la etiqueta |
| Barra de mes | `.monthbar` + `.monthbar-actions` | filete de cierre; secundario en `.lnk`, principal en `.btn-primary` |
| Banda de KPIs | `.kpiband` | tres columnas con filete vertical; a 860px se apilan |
| Aviso | `.warnline` + `.warndot` | punto en vez de emoji, sin caja de color |
| Sección | `.sheet` + `.sheet-head` + `.sheet-title` + `.sheet-2` | hoja separada por filete; `.card` no se usa en el panel |
| Categorías | `.catrow` | sin barras de colores; nombre, importe y variación |
| Cuentas | `.acct` | punto de color de la cuenta (es dato), sin barra |
| Previsión / totales | `.fcrow` | dos columnas con punteado |
| Gráfico | `.chart-box.chart-tall` | línea en `--text` a 1,6px, sin relleno, punto rojo solo en el último mes |

## Qué NO hacer en esta superficie

- Nada de `.card`: el panel es hoja y filete. Si algo necesita caja, es que va en otra pantalla.
- Nada de serif en las cifras de tabla ni de categoría. Serif es hero, titulares y KPIs.
- Nada de rojo que no sea la marca, "Importar", el punto de aviso o un importe negativo.
- Ni emoji, ni barras de colores por categoría, ni relleno bajo la línea del gráfico.

## Validación (2026-09-08)

- [x] Comparación con el boceto: `explorations/panel-refs/our-build-<fecha>.png`,
      que se queda **solo en local** — sale de la app con saldos y comercios reales,
      y `.gitignore` lo excluye
- [x] 1440, 1024, 768 y 375 en navegador real, sin scroll horizontal
- [x] Tema claro y tema oscuro
- [x] `prefers-reduced-motion` respetado (regla global al final de `tnt.css`)
- [x] `ui-vocabulary-check`: 0 hallazgos en `dashboard.html` (la app entera baja de 31 a 27)
- [x] 88 tests en verde

## Pendiente

- ~~La fecha en ISO~~ **resuelto el 2026-09-09**: filtro `| fecha` → `31/08/2026`.
  El boceto usaba `31/08` sin año, pero se eligió un único formato para toda la app:
  ocupa lo mismo que el ISO y no hay dos reglas que recordar.
- Las otras once pantallas siguen en `.card`. Migran cuando les toque, una a una.

## El panel vacío (2026-09-09)

`dashboard_empty.html` es lo que se ve antes del primer movimiento: la primera
pantalla de TNT para quien acaba de instalarlo. Era la única que no había pasado
por el rediseño, y no por estética: **estaba rota**. Usaba `.empty-bolt` para
darle tamaño a un rayo SVG y esa clase no existía en el CSS, así que el SVG se
estiraba a 1185 × 1580 px y empujaba el texto y el botón 1.600 px hacia abajo.
Solo aparece con la base vacía, así que llevaba meses así sin que nadie la viera.

Ahora habla la lengua del resto: `.pagehead` con el titular serif, una sola
acción roja («Importar extracto») y una hoja «Por dónde empezar» con tres filas
`.settings-row` —las mismas de Configuración— que llevan a las tres maneras
reales de meter datos: extracto del banco, histórico de HomeBank, o a mano. Cero
CSS nuevo. Se queda la letra de AC/DC al pie, que es la voz de la casa.

Fuera el rayo gigante: la marca ya está en la barra de arriba, y un adorno
grande en el centro es justo el aspecto «generado» del que huye la dirección.

## Rendimiento (2026-09-09)

Medido sobre una copia de la base real (9 cuentas, 947 movimientos):

| | consultas | tiempo |
|---|---|---|
| de partida | 107 | 75 ms |
| saldos en bloque | 77 | 77 ms |
| recurrentes sin N+1 | **36** | **48 ms** |

Y las 36 se quedan en 36 con 100 cuentas. Lo que quedaba después de aplanar los
saldos era `detect_anomalies`, que preguntaba a la base cuál era el último
movimiento de cada recurrente —una consulta por grupo, 37 en la base real— para
un dato que `find_recurring` ya tenía en la mano. Ahora el grupo se lo lleva
puesto (`last_id`, `last_amount`).

Además, `forecast` buscaba los recurrentes dos veces, y cada búsqueda es leer la
tabla de movimientos entera y reagruparla en memoria. Ahora una.

El panel renderiza **el mismo HTML byte a byte** que antes del cambio.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-08 | Dirección "papel", en oscuro | elegida sobre cuatro bocetos |
| 2026-09-08 | Pareja E: serif salvo la tabla | carácter donde se mira despacio, precisión donde se compara |
| 2026-09-08 | Fuera la sparkline del hero | repetía la serie del gráfico grande |
| 2026-09-08 | Fuera las barras de colores por categoría | eran ocho literales en la plantilla y el boceto pide filas limpias |
| 2026-09-08 | La franja de backup baja al final | es utilidad, no contenido: no debe partir el hero de las cifras |
| 2026-09-09 | La franja de backup **se va del panel** | tras la reestructuración de menús vive en Configuración · Backup; tenerla también aquí era el mismo botón en dos sitios |
| 2026-09-08 | El segmentado Saldo/Neto deja de ser rojo | el rojo sólido se reserva a la acción principal |
| 2026-09-09 | El panel vacío pasa a hoja y filete, sin rayo decorativo | era la única pantalla sin migrar, y encima la clase que dimensionaba el rayo no existía |
| 2026-09-09 | La sublínea del hero se alinea con la cifra | `.wrap` le metía 24px de sangrado que nadie quería |
