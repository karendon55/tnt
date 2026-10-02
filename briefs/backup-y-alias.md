# Backup y Alias — brief de diseño

Estado: **bloqueado** · Fecha: 2026-09-09

## Qué son estas superficies

`/backup` guarda copias de la base en carpetas locales, en plano o cifradas con
contraseña, y permite volver atrás desde un `.tnt`. `/alias` traduce descripciones
ilegibles del banco a nombres que se entienden. Las dos viven en Configuración y se
tocan poco, pero cuando se tocan importa mucho no equivocarse.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-09-09 | Fuera los cinco emoji de Backup (🔒 🔁 ⚙ 💾 ⬇ ↩) | el estado lo dicen la palabra y el color |
| 2026-09-09 | Cada destino es una fila con punteado, no una caja dentro de otra | tenía `style="background:rgba(0,0,0,0.15)"`, el último literal suelto de la app |
| 2026-09-09 | La acción roja de Backup es **Hacer backup ahora**; Restaurar se queda en `btn-danger` | son tokens distintos: uno es la acción principal, el otro avisa de que destruye |
| 2026-09-09 | El JS de los campos de contraseña usa `hidden`, no `style.display` | el vocabulario visual vive en el CSS, también cuando lo cambia el JS |
| 2026-09-09 | En Alias, editar y borrar pasan a iconos con `aria-label` | mismo patrón que Reglas, Cuentas y Movimientos |
| 2026-10-02 | En Backup, la fila de la base parte línea (`wrap-w`) y las rutas llevan `.break-any` | a 375px la ruta, sin espacios, echaba las píldoras fuera: la página medía 607px. Solo esa fila: con `wrap-w` en todos los `.warnline-top`, el punto de un aviso largo se quedaría solo arriba |
| 2026-10-02 | La tabla de Alias va en `.table-scroll` | a 375px medía 527px y empujaba la página; ahora se desliza dentro de su caja |

## La trampa que apareció al probar

Los destinos de backup son los mismos en cualquier sesión: `~/Dropbox` y la carpeta de
contabilidad. Con el servidor en **modo demostración**, pulsar «Hacer backup» habría
copiado la base de mentira **encima de las copias buenas**. El agujero lo abrió el propio
modo demo, así que se cierra ahí: en demo, los dos caminos de escritura devuelven un
aviso en vez de copiar. La pantalla se sigue viendo entera —bloquear la escritura no es
esconder la sección— y cuatro tests lo fijan.

## Validación (2026-09-09)

- [x] Las dos pantallas responden y se leen en hoja y filete
- [x] El selector de cifrado enseña y oculta los campos de contraseña, y marca
      `required` solo cuando toca — sin escribir `style` desde el JS
- [x] En demo, `/backup` y `/backup/destino` devuelven el aviso y **no escriben**:
      la copia real del 04/09 sigue intacta
- [x] Los acentos sobreviven el viaje: «Panadería Ñoño» se guarda y se pinta bien
- [x] Cero `style=`, cero `.card`, cero emoji y **cero literales de color en toda la app**
