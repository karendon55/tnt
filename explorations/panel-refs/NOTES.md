# Panel · Fase 3, un componente (el hero)

Referencia: `explorations/panel-papel-oscuro/index.html`, que ya abre en el estado
bloqueado (pareja E, fondo neutro). Capturas de esta fecha en este mismo directorio:
`boceto-2026-09-08.png`, `our-build-2026-09-08.png` y el montaje `diff-hero-2026-09-08.png`.

## Qué se ha construido

Solo el hero del patrimonio, sobre tokens reales de `tnt.css`:

- `--font-display` pasa de Impact a `Georgia, "Noto Serif", serif`; nace `--font-brand`
  con Impact para que la marca del topbar siga siendo AC/DC.
- `.sheet`: sección plana separada por filete, para ir sustituyendo a `.card` pantalla
  a pantalla. `.card` no se toca.
- `.hero` deja de ser tarjeta: sin fondo, sin borde, sin el degradado radial rojo que
  tenía (era justo el "SaaS genérico" que la anti-estética descarta).
- La sparkline pierde el relleno y baja a 1,6px, como en el boceto. De paso se va el
  `rgba(225,6,0,.11)` literal de la plantilla: 31 hallazgos en `app/` pasan a 30.

## Deltas frente al boceto

1. ~~**Orden de la página.**~~ **Hecho el 2026-09-08.** El hero es lo primero; debajo va
   `.monthbar` (mes, píldora de "último mes con datos" y acciones) cerrada por un filete.
   El `<h1>` ya no es "Panel": lo es la etiqueta "Patrimonio total" del hero, como en el
   boceto, así que la página sigue teniendo un solo h1.
2. **Botones.** El boceto usa enlaces subrayados; la app tiene botones con caja y un
   "Importar" en rojo sólido. Decidir cuáles sobreviven: la dirección pide enlace para
   lo secundario y rojo solo para la acción principal.
3. **Tarjeta de backup.** Sigue siendo una caja redondeada y lleva emoji, que el
   design-system prohíbe en interfaz.
4. **Avisos.** El bloque de anomalías usa el emoji 🔁; hay que sustituirlo.
5. ~~**Sparkline en el hero.**~~ **Retirada el 2026-09-08**, con su bloque de Chart.js.
   Contaba la misma serie que "Evolución del saldo", unos centímetros más abajo.

## Trampa encontrada (anotada en tnt.css)

`.wrap` hace dos cosas en `tnt.css`: es el contenedor de 1280px (`width:100%`) y la
utilidad de `flex-wrap`. Dentro de una fila flex hay que usar `.wrap-w`; con `.wrap`, el
hijo se come la fila entera. Le costó una iteración a la barra de mes.

## No-regresión

Movimientos y Categorías comprobadas a 1440: sin cambios salvo la tipografía heredada.
La marca sigue en Impact.

## Hallazgo ajeno al rediseño

La serie del saldo devuelve **seis puntos idénticos** (`una cifra de seis dígitos` en los seis meses),
así que la sparkline dibuja una recta. No es CSS: es el cálculo de la serie. Bug aparte.
