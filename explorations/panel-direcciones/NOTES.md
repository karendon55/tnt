# Panel · Fase 0, boceto de dirección

Fichero suelto (`index.html`), sin Jinja, sin Basecoat, sin servidor: se abre a pelo
en el navegador. Mismo contenido del panel real en cuatro tratamientos distintos.
No es código para la app; es para elegir.

Qué cambia entre direcciones (no solo el color): fondo, jerarquía tipográfica,
densidad, radios, acento y movimiento.

| # | Dirección | Fondo | Tipografía | Densidad | Radios | Acento |
|---|---|---|---|---|---|---|
| 1 | Sala de máquinas | negro #0a0a0a | sistema, Impact en la marca | alta | 5px | rojo AC/DC, único |
| 2 | Papel | hueso #f6f3ed | Georgia en cifras y titulares | baja | 0 | rojo granate solo en negativos |
| 3 | Instrumento | grafito #131519 | monoespaciada en todas las cifras | media | 13px | plata manda, rojo = alarma |
| 4 | Lista | casi blanco #fbfbfa | sistema, escala pequeña | máxima | 0 | rojo mínimo, un punto |

Las cuatro respetan la anti-estética acordada: ni SaaS genérico (sin degradados ni
tarjetas flotando), ni app bancaria (sin ilustraciones ni emoji), ni hoja de cálculo
(sin rejilla ni bordes en cada celda).

## Decisión

- Dirección elegida (2026-09-08): **2 · Papel, pero en oscuro**, sobre el fondo que TNT
  ya tiene. No es la 2 tal cual: se conserva su estructura y su tipografía, cambia el fondo.
- Qué robamos de ella: la cifra hero en serif y grande; nada de tarjetas —filetes y aire
  hacen la estructura—; radios 0; el rojo solo en lo negativo, la marca y la acción principal;
  las tres columnas de KPI separadas por filete vertical; las filas de categoría con punteado.
- Qué descartamos de las otras: la densidad y el borde por todas partes de la 1; el arco
  medidor y la monoespaciada total de la 3; la compresión de la 4 (buena para movimientos,
  demasiado apretada para el panel).
- La línea que va a `design-system.md`: "papel en oscuro — fondo casi negro, serif en cifras
  y titulares, sin tarjetas, el rojo AC/DC reservado a la marca, a la acción principal y a
  lo negativo".
- Siguiente paso: cerrar la pareja tipográfica en `explorations/panel-papel-oscuro/`.
