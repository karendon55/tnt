# Inversiones — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué es esta superficie

`/inversiones`. Un fondo cambia de valor sin que haya movimientos, así que su saldo
no sale de sumar aportaciones. Aquí se declara, una vez al mes con el informe de la
entidad, y se ve el hueco entre lo aportado y lo que vale. Salió de dentro de Cuentas
el 2026-09-08.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | Cada fondo es una hoja, no una tarjeta dentro de otra | eran cajas anidadas con un `rgba` a mano de fondo |
| 2026-09-09 | Las tres cifras usan la banda de KPIs del panel | mismo patrón, filetes verticales, serif |
| 2026-09-09 | El formulario de valoración usa la fila de filtros de Movimientos | alcanzar el patrón antes que inventar otro |
| 2026-09-09 | **Guardar valoración** se queda en rojo aunque se repita por fondo | es la misma acción repetida, no dos compitiendo: la regla veta acciones rivales en rojo, no un listado |
| 2026-09-09 | La línea de valor pasa a tinta y pierde el relleno; el rojo marca solo el último punto | igual que la curva del panel |
| 2026-10-02 | El histórico de valoraciones va en `.table-scroll` | a 375px medía 425px dentro del desplegable, que lo cortaba en el borde: la nota se truncaba y el botón de borrar quedaba fuera, sin forma de llegar a él |
| 2026-11-03 | Las tres cifras del fondo llevan los céntimos en voladita (`eur_cifra`) | tercera referencia del sistema (Mercury), igual que en el panel |
| 2026-11-03 | Aquí no van las filas de dos líneas de esa referencia | hay un solo fondo: una lista de una fila no ordena nada; van en Cuentas |

## Qué NO hacer aquí

- Ni tarjetas anidadas: cada fondo es una hoja separada por filete.
- Ni relleno bajo las líneas: el hueco entre valor y aportado es la historia.
- Ni fondos de color escritos a mano.

## Validación de los céntimos en voladita (2026-11-03)

- [x] Captura con un fondo inventado: `explorations/inversiones-refs/demo-cifras-2026-11-03.jpg`
- [x] 1440 y 375 en navegador real, sin scroll horizontal
- [x] El texto que se lee no cambia («21.378,91 €»); sin valoración sigue la raya
- [x] 410 tests en verde

## Validación (2026-09-09)

- [x] 1440 y 375 en navegador real
- [x] Tema claro y tema oscuro, **incluido el cambio en caliente**: el gráfico se
      repinta al cambiar de tema, que era el fallo que introdujo la línea de tinta
- [x] Cero `style=` y cero emoji en `investments.html`
- [x] Borrar valoración con `aria-label` que nombra fecha y fondo
