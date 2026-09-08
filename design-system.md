# Design System — TNT

Fuente de verdad visual del proyecto. Se actualiza **antes** de generar componentes,
nunca después. Los tokens reales viven en `app/static/css/tnt.css`; este documento
dice qué está bloqueado y qué no se puede inventar en el punto de uso.

## Brand foundation

- **Proyecto**: TNT — Tus Números Tranquilos (finanzas personales, local, sustituto de HomeBank).
- **Intención estética (una línea)**: **papel en oscuro** — fondo casi negro, serif en
  cifras y titulares, sin tarjetas (filetes finos y aire hacen la estructura), y el rojo
  AC/DC reservado a la marca, a la acción principal y a lo negativo.
  Decidido el 2026-09-08 sobre los bocetos `explorations/panel-direcciones/` (dirección) y
  `explorations/panel-papel-oscuro/` (tipografía y fondo).
- **Anti-estética, lo que NO somos**:
  - No SaaS genérico: sin degradados, sin tarjetas flotando con sombras, sin el look "plantilla de Tailwind".
  - No app bancaria: sin ilustraciones corporativas, sin mensajes paternalistas, sin emojis en la interfaz.
  - No hoja de cálculo: sin rejilla de Excel a pelo, sin bordes en todas las celdas.
- **Referencias visuales bloqueadas** (capturas en `explorations/<superficie>-refs/`):
  1. **shadcn charts + Tremor** — qué robamos: tratamiento de gráficos sobre los mismos
     tokens semánticos que ya usa Basecoat (ejes tenues, una sola serie acentuada,
     leyenda discreta, tooltips sin sombra dura).
  2. **`explorations/panel-papel-oscuro/index.html`** (referencia interna, bloqueada) — qué
     robamos: la cifra hero en serif a 64px, la banda de tres KPI separada por filetes
     verticales en vez de tarjetas, las filas de categoría con filete punteado, y el
     gráfico de línea a 1,4px sin relleno.
  3. PENDIENTE.

## Color: variables CSS, nunca literales en plantillas

Todos los colores viven en `app/static/css/tnt.css` (`:root` y `:root[data-theme="dark"], .dark`)
y se consumen por token semántico. Contrato shadcn/Basecoat: `--background`, `--foreground`,
`--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent-bg`, `--destructive`,
`--border`, `--input`, `--ring`, cada uno con su `-foreground`.

Alias propios de TNT sobre ese contrato: `--bg`, `--surface`, `--surface-raised`,
`--surface-hover`, `--border-strong`, `--text`, `--text-muted`, `--text-subtle`,
`--accent`, `--accent-hover`, `--accent-soft`, `--silver`, `--success`, `--warning`,
`--danger`, `--chart-grid`.

- Acento único: rojo AC/DC `--accent` (`#e10600`), con `--accent-hover` y `--accent-soft`.
  No hay segundo acento; añadir uno exige editar antes este fichero.
- **Fondo neutro** (decidido el 2026-09-08): el negro que ya tiene TNT, sin virar a cálido.
- **El rojo puro no se usa en texto pequeño sobre oscuro**: `#e10600` queda para la marca, la
  acción principal y el punto de aviso; los importes negativos usan `--danger` (`#f87171` en
  oscuro), que es lo que ya hace `tnt.css`.
- Semáforo de importes: `--success` positivo, `--danger` negativo, `--warning` aviso. Nada más.
- Los dos temas (claro y oscuro) son obligatorios: todo token nuevo se define en ambos bloques.
  El tema claro de la dirección es el boceto 2 original (fondo hueso), no un negativo mecánico.

## Tipografía

Pareja bloqueada el 2026-09-08: **serif en todo salvo la tabla** (opción E del boceto).
La frontera es la regla, no el gusto: **serif donde se mira despacio, sans donde se compara
deprisa**. Si una cifra de tabla se pone en serif, la dirección se rompe.

- **Display**: `--font-display` → `Georgia, "Noto Serif", serif`. Titulares de sección, la
  cifra hero del patrimonio y los tres valores de KPI. Peso normal, nunca negrita en cifras.
- **Cuerpo**: `--font-sans`, stack del sistema. Base 15px, `line-height` 1.5. Etiquetas,
  navegación, descripciones y **todas las cifras de tabla y de categoría**, con `tabular-nums`.
- **Mono**: `--font-mono` (SFMono / Menlo / Consolas) solo para códigos, IDs y etiquetas
  técnicas. Nunca para importes.
- Georgia está instalada en esta máquina; el stack cae a Noto Serif donde no lo esté, y esa
  caída tiene que seguir siendo aceptable (es la opción B del boceto).
- Escala en uso: `.t-xs` .72rem · `.t-sm` .82rem · `.t-base` .94rem · base 15px ·
  `h3` 1.05rem · `h2` 1.25rem · `h1` 1.7rem. Solo estas.
- Titulares: `line-height` 1.25, `letter-spacing` -.02em.
- Cifras: siempre `.tabular` / `.num` (`tabular-nums`) en tablas y KPIs.
- **Cero fuentes web.** Hoy no se carga ninguna; no se añade ninguna sin actualizar este fichero.

## Espaciado y radios

- Espaciado por utilidades existentes: `.g1` .25 · `.g2` .5 · `.g3` .75 · `.g4` 1 · `.g6` 1.5rem;
  márgenes `.mt1`…`.mt6`. Ancho de contenido 1280px, padding lateral 1.5rem.
- Radios: `--radius-sm` .4rem · `--radius-md`/`--radius` .65rem · `--radius-lg` .9rem. Nada por encima.
  `border-radius:50%`/pill solo en avatares y chips.
- Bordes de 1px, color `--border` (o `--border-strong` cuando hace falta contraste).

## Sombras

- `--shadow-sm` tarjetas en reposo · `--shadow-md` elevado u hover. No hay una tercera.
- Sin sombra en superficies planas ni en botones.

## Movimiento

- Transiciones cortas: `.12s` en fondo y borde de controles (contrato actual de `tnt.css`).
- Única animación viva: `.bolt-loading` (pulso del rayo) como indicador de carga.
- Sin física de muelle. Todo debe poder colapsar bajo `prefers-reduced-motion`.

## Botones

- Primario: sólido sobre `--accent`, sin degradado y sin sombra. Secundario: contorno.
  Terciario: fantasma. Enlace de acción (`.lnk`): subrayado fino, sin caja.
- **Una sola acción en rojo sólido por pantalla.** Marcar el estado —la pantalla activa
  de la navegación, la serie que estás viendo— no es una acción: eso va subrayado o en
  gris. El texto sobre sólido usa `--primary-foreground` / `--danger-foreground`, nunca
  `#fff` a pelo.
- Nunca: botones con degradado, sombra en botones, radios enormes, glow en las llamadas a la acción.

## Iconos

- SVG en línea, trazo `stroke-width:2`, `currentColor`. Tamaños 16px en línea, 20px sueltos.
  El rayo de la marca es la única forma de identidad.
- **Sin emoji en la interfaz, nunca.**

## Librerías (máximo dos por superficie)

- **Basecoat CSS** (CDN) aporta reset y componentes; `tnt.css` mapea su contrato de tokens.
- **htmx** para interacción; **Chart.js** para gráficos, siempre leyendo colores con
  `getComputedStyle` sobre los tokens, nunca con literales.

## Reglas para el agente

1. Cada pantalla es una pieza de portfolio: "diseñada por un equipo", no "generada".
2. Si falta un color, una fuente, un radio, una sombra o una curva de movimiento, se añade
   **primero aquí y a `tnt.css`**, y después se usa. Nunca se inventa en el punto de uso.
3. Los componentes de Basecoat se personalizan (hover de botón, sombra de tarjeta, anillo de
   foco); los valores por defecto son el look generado.
4. Antes de un componente nuevo: 3 a 5 referencias en `explorations/<superficie>-refs/` y
   qué robamos de cada una en `NOTES.md`.
5. Después de cada componente: captura en el navegador real y comparación con la referencia
   antes de darlo por hecho.

## Lo que NO se hace

- Sin serif en cifras de tabla ni de categoría: rompe la frontera de la pareja tipográfica.
- Sin colores literales (`#hex`, `rgb()`, `hsl()`) en `app/templates/`. Van a `tnt.css` como token.
- Sin atributos `style="..."` con valores literales en las plantillas.
- Sin `text-shadow`. Sin `backdrop-blur` sobre texto (el de la topbar es sobre fondo, y se queda).
- Sin `animate-pulse` salvo esqueletos de carga.
- Sin emoji en el copy. Sin más de dos fuentes web (hoy: cero).
- Copy en español, capitalizado al empezar, sin jerga técnica visible ("500 Internal Server Error" no se enseña).

## Deuda conocida

`ui-vocabulary-check.py audit` da **221 hallazgos** (todos COLOR), de los cuales **31 en `app/`**
(31 en plantillas y `tnt.css`) y 190 en `mockups/`. No se reescriben: el hook solo bloquea
hallazgos **nuevos**. Se migra un fichero cuando ya se está tocando por otro motivo.

## Briefs por superficie

Las superficies bloqueadas llevan `briefs/<superficie>.md` (plantilla en la sección 2.7 de
`~/.claude/standards/ENGINEERING-AND-DESIGN.md`).
