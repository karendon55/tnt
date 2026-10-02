# TNT — Estado del proyecto

Documento de contexto para retomar el trabajo sin releerlo todo. Recoge el
**estado**, el **porqué** de lo que no es obvio y las **trampas** que ya han
mordido. El detalle de cada decisión está en `docs/QUESTIONS.md`; aquí solo lo
que hace falta para orientarse.

Última actualización: **1 de octubre de 2026**. Proyecto iniciado el 21 de abril.

---

## 1. Qué es

Aplicación local de finanzas personales para sustituir a HomeBank. Corre en
`localhost:8000`; los datos bancarios no salen del equipo.

| | |
|---|---|
| Backend | Python · FastAPI · Uvicorn · SQLite (sin ORM, SQL a mano) |
| Plantillas | Jinja2 renderizado en servidor, HTMX 1.9.10, sin framework JS |
| Estilos | sistema propio **"papel en oscuro"** sobre la base de Basecoat |
| Gráficos | Chart.js 4.4.1 |
| Tamaño | 5.800 líneas de Python, 2.800 de plantillas, 590 de CSS, 212 tests |

Basecoat y Chart.js se cargan por CDN. Es deliberado: "100 % local" se refiere
a **los datos**, no a los assets.

---

## 2. Dónde está cada cosa

La documentación está repartida; esto es el mapa.

| Fichero | Para qué |
|---|---|
| `progreso.md` | este: estado, porqués y trampas |
| `docs/QUESTIONS.md` | **registro de decisiones**, una por línea (83). Leer antes de preguntar nada: lo respondido está cerrado salvo que el usuario lo reabra |
| `design-system.md` | el lenguaje visual: tokens, tipografía, qué no se hace, deuda |
| `briefs/*.md` | una por pantalla (10), con lo que vale y no vale en cada una |
| `explorations/` | los bocetos de los que salió el diseño |
| `CLAUDE.md` | convenciones del repo para el agente |
| `HANDOFF.md` | ⚠️ **histórico, de abril**. Ver la trampa de la sección 5 |
| `docs/Manual-TNT.*` | manual de usuario, **desfasado** (mayo) |

---

## 3. Lo que ya funciona

**Navegación.** Arriba, lo que se hace cada mes: Panel, Movimientos, Traspasos,
Inversiones, Presupuestos. En **Configuración**, lo de vez en cuando: Backup,
Cuentas, Categorías, Reglas, Importar y Alias. El mapa vive en
`app/navigation.py` y las URLs antiguas siguen funcionando.

**Importación.** ING y CaixaBank (XLS), EuroCaja Rural (CSV) y HomeBank (CSV,
con cuenta destino a elegir porque el fichero no trae IBAN). Preview, confirmar
y deshacer un lote entero.

**Categorización.** Reglas integradas, aprendidas y manuales; aprende de las
correcciones y sugiere reglas nuevas.

**Panel.** Patrimonio en grande con lo que varió en el mes que se ve, selector
de mes, banda de KPIs del mes con su variación, avisos, gasto por categoría, evolución de saldo o neto mensual,
últimos movimientos, previsión y desglose de cuentas.

**Inversiones.** Cuentas cuyo valor marca la última valoración declarada, con
aportado, valor, rentabilidad y la curva de los dos.

**Backup.** Por destino, cifrado o plano; la contraseña, protegida con clave
maestra. Restauración desde `.tnt`.

**Modo demostración.** `./run.sh --demo` levanta TNT sobre una base inventada
(`scripts/make_demo_db.py`) para probar sin riesgo. Una píldora en la barra lo
avisa, y el backup se bloquea para no pisar las copias reales.

**Empaquetado.** `install.sh` instala con icono y lanzador; `package.sh` genera
el distribuible.

---

## 4. Decisiones de diseño (el porqué)

### Los traspasos no son ingresos ni gastos
La regla estructural de la aplicación. Mover dinero entre bolsillos propios no
es actividad económica: dos movimientos emparejados (`transfer_id`) quedan
fuera de los KPIs, del gasto por categoría y del neto. Ha reaparecido con
cuatro caras: un depósito de 150.000 € contado como gasto, su cancelación como
ingreso, el Bizum recibido restando, y la rentabilidad de un fondo que habría
inflado los ingresos. **Ante cualquier importe raro en los KPIs, mirar esto
primero.**

### Un fondo no se valora sumando movimientos
Una cuenta bancaria vale lo que suman sus apuntes; un fondo cambia de valor sin
que ocurra nada. Las cuentas `type='investment'` toman su saldo de la **última
valoración declarada** (`account_valuations`). Anotar la revalorización como un
apunte la convertiría en ingreso del mes. La única función que aplica esta
regla en bloque es `balances_by_account`, y un test la ata cuenta por cuenta a
`account_balance`.

### En las reglas gana la específica, no la frecuente
Desempate: **manual → patrón más largo → priority × hits**. Antes ganaba la más
repetida, y `REPSOL` (aprendida de los recibos de luz) mandaba la gasolina de
`REPSOL WAYLET` a "Luz y gas". Las aprendidas **se revocan** cuando su
evidencia baja del 70 %.

### Una petición que escribe es una transacción
`cursor()` abre la transacción y la cierra al salir. Enlazar un traspaso son dos
UPDATE; un movimiento espejo, un INSERT y dos UPDATE: sin transacción, un fallo
a medias dejaba un traspaso cojo. Para lotes donde un elemento malo no debe
tirar los buenos, `savepoint(cur, nombre)`.

### Una pantalla, un sitio
Si algo aparece en dos menús, la regla de reparto no está clara. Por eso
Traspasos vive solo arriba y el backup salió del panel.

### El rojo es escaso
El rojo sólido se reserva a la acción principal de cada pantalla (una, o
ninguna si ninguna lo es), la marca, el punto de aviso y los importes
negativos. Lo destructivo usa `--danger`, que es otro token.

### La contraseña de backup no vive en la base de datos
Se cifra con la clave maestra de `~/.config/tnt/master.key` (permisos 600),
fuera de todo lo que se respalda. Si se pierde ese fichero, el backup cifrado
solo se restaura tecleando la contraseña a mano.

---

## 5. Trampas conocidas

### El código instalado no es el del repo, pero la base sí es la misma
El código vive en `/home/trooper/IA` y la app corre desde
`~/.local/share/tnt`, que es **otra copia**: editar el repo no cambia lo que se
ve hasta `./packaging/install.sh --no-venv` y reiniciar. Si se reinstala con TNT
abierto, el proceso sigue con el código viejo en memoria.

En cambio la **base de datos es una sola**: `.env.local` (fuera de git) apunta
`TNT_DB` a la real. Así que `./run.sh` desde el repo trabaja **sobre dinero de
verdad**: cualquier prueba de importar, restaurar o borrar lo toca. Para
experimentar, `./run.sh --demo`.

### `HANDOFF.md` aconseja algo que ahora rompe
Dice que la conexión va en autocommit y que se envuelva cada escritura en
`BEGIN`/`COMMIT`. Ya no: `cursor()` abre su propia transacción, y un `BEGIN`
manual dentro provoca *cannot start a transaction within a transaction*. El
resto de sus trampas (abajo) siguen vigentes.

### Los gastos se guardan en negativo
`month_income_expense` devuelve `expense` como suma de importes negativos. Al
comparar meses, un gasto **mayor** es un número **más negativo**, y la resta
directa da el signo cambiado: el panel dijo «▼ 99,5 %» en verde cuando el gasto
de septiembre casi se duplicó. Toda variación sobre gastos va sobre magnitudes
(`_variacion_pct` en `app/routers/dashboard.py`).

### Basecoat pone `display:flex` en `.card`, y los diálogos son `.card`
Eso gana al `display:none` con que el navegador oculta un `<dialog>` cerrado, y
aparecían desplegados en la página. Lo corrige `dialog:not([open])`. Los siete
`.card` que quedan en plantillas son todos diálogos.

### Chart.js: altura fija, y colores leídos al pintar
Sin un padre de altura definida y con `maintainAspectRatio:false`, el lienzo
crece en cada redibujado (llegó a 36.000 px): todo gráfico va en `.chart-box`.
Y Chart.js **copia** los colores al construirse: al cambiar de tema sin
recargar, una línea en color de tinta se volvía invisible. Por eso se leen
dentro de la función que pinta, y esa función se registra en
`window.tntRepintar`: `tnt.js` las llama todas al cambiar de tema. **Un gráfico
nuevo que no se registre se quedará con los colores del tema anterior.**

### htmx no ve lo que hay dentro de un `<template>`
Busca los fragmentos OOB con `querySelectorAll`, que no entra en el contenido de
un `<template>`. Envolver un `<td>` OOB así lo hacía invisible: el swap no
ocurría nunca. Se apunta a un `<span>`.

### El orden de las hojas de estilo es la cascada
Cinco `<link>` en `base.html`: tokens, base, componentes, patrones, pantallas.
Reordenarlos cambia el resultado sin tocar una regla; lo fija un test. Sin
`@import`, que serializa las descargas.

### Las tablas anchas se recortan, no se desplazan
Una tabla que se pasa del ancho pierde sus últimas columnas en silencio. Patrón:
`.table-scroll` + `.table-fixed` + `<colgroup>` con anchos en CSS. Si una columna
se oculta en el móvil, los anchos van en las cabeceras y no en `<col>`. Las celdas
no parten línea (Basecoat les pone `nowrap`), así que una tabla sin
`.table-scroll` acaba empujando la página.

Y si la tabla va en una rejilla, la pista es `minmax(0,1fr)`: una `1fr` a secas
no baja del ancho mínimo de su contenido, y una tabla así empujó el panel a
598 px en una pantalla de 375. Se comprueba midiendo, no mirando:
`scrollWidth` igual a `clientWidth`.

### SQLite en modo WAL y las copias
Lo confirmado vive en `tnt.db-wal` hasta el checkpoint: copiar `tnt.db` a pelo
pierde lo último. Los backups usan `db_snapshot()`. Al restaurar hay que borrar
`-wal` y `-shm`, o SQLite aplicará el WAL viejo sobre la base nueva.

### Los IBAN vienen en dos formatos
IBAN completo (`ES99…`, 24 caracteres) o BBAN (20 dígitos). Comparar en crudo
duplicaba cuentas al importar; `ensure_account` normaliza y, si no encaja,
compara por los últimos 20.

### Heredadas de `HANDOFF.md`, siguen vigentes
- `TemplateResponse(request, "x.html", {...})`: la firma antigua, con `request`
  dentro del diccionario, da `TypeError`.
- Los `.xls` de los bancos son BIFF antiguo, que `openpyxl` no lee: se
  convierten con `ssconvert` (Gnumeric).
- ING trae mojibake (`¥` en lugar de `Ñ`): todo parser nuevo pasa por
  `clean_text()`.
- La deduplicación usa `tx_hash()` (IBAN, fecha, importe, descripción, saldo).
  Cambiarlo rompe las bases existentes: reimportar dejaría de reconocer lo que
  ya está.

### Los avisos (`msg`, `err`) viajan en la URL
Tras guardar, la redirección lleva el aviso en la query string, y esa URL queda
en el historial del navegador, que puede sincronizarse fuera de la máquina.
Ningún importe en un aviso: la cifra ya está en la pantalla a la que se vuelve.

### Al iterar un cursor de SQLite, `fetchall()`
Reutilizar el mismo cursor dentro del bucle invalida la iteración y solo se
procesa la primera fila.

---

## 6. Datos del usuario (contexto)

1.108 movimientos de enero a septiembre de 2026, en 9 cuentas activas.

- **Indexa Capital**, de tipo inversión: 60.440 € aportados y 63.759,24 € de
  valor en septiembre, con 9 valoraciones. Las aportaciones son anteriores al
  histórico de TNT, por eso son saldo inicial y no movimientos: no hay
  contrapartida bancaria con la que emparejarlas.
- **Plan pensiones Olga** sigue de tipo banco por decisión del usuario, con sus
  14.650 € aportados; su valor real será otro. **No tocar.**
- **Dos depósitos de EuroCaja Rural** (anual al 2,30 %, vence 20/08/2027; nueve
  meses al 3,00 %, vence 14/02/2027), con reglas de traspaso en los dos
  sentidos.

---

## 7. Pendiente

**Resuelto (1/10/2026): las reglas de los depósitos.** Las reglas de traspaso
admiten ahora un importe exacto: 60.000 € van al de nueve meses y 150.000 € al
anual. Un depósito nuevo de otro importe no casa con ninguna y sale en los KPIs
como gasto: hay que crearle su cuenta y sus dos reglas.

**Resuelto (2/10/2026): la fecha de las valoraciones.** El formulario propone
ahora el último día del mes anterior, que es la fecha del informe, y al guardar
dice qué fecha ha quedado. La de septiembre pasó del 01/10 al 30/09: la curva ya
no tiene punto de octubre y la subida de septiembre (+424,98 €) cae en su mes.

**Resuelto (2/10/2026): la línea bajo el patrimonio.** Era el neto del mes, que
repetía su tarjeta y no contaba lo que gana o pierde el fondo. Ahora es la
variación del patrimonio en el mes que se ve (cierre menos cierre del anterior),
cuadra con la curva y nombra el mes: «▲ 4.964,10 € en septiembre 2026».

**Categorías solapadas.** Conviven `Transferencias` (1 movimiento) y
`Otros gastos | Transferencias` (5). Mismo caso que "Bizum enviado", que ya se
unificó; falta decidir cuál sobrevive.

**Documentación.** El manual es de mayo: no recoge el rediseño, la navegación
nueva, las inversiones ni el modo demostración. `HANDOFF.md` habría que
archivarlo o borrarlo, porque su consejo sobre transacciones ya no vale.

**Rendimiento.** El 58 % del tiempo del panel es la consulta de duplicados de
`detect_anomalies`: un JOIN de `transactions` consigo misma sin cota de fechas.

**Ficheros sobre el tope blando de 350 líneas**, por debajo del duro de 500:
`analytics.py` (455), `backup.py` (426), `transactions.py` (409),
`import_page.py` (397).

**Diseño, pendiente del usuario.** La intención estética de TNT en una línea, y
dos de las tres referencias visuales.

**Pequeños.** En los KPIs, un mes sin cambios sale «▲ 0,0 %» en verde, cuando
debería ir neutro (la línea del patrimonio ya lo hace). Cinco tablas siguen sin
`.table-scroll` en estados que no se han medido en el móvil: el historial de
valoraciones de Inversiones (dentro de un desplegable), dos en los diálogos de
Cuentas, y la vista previa y el resultado de importar. Y una idea sin
desarrollar: comparar la rentabilidad del fondo con su benchmark, que Indexa
envía en el mismo correo.

**Resuelto (2/10/2026): el móvil.** Las trece pantallas caben a 375 px, medido
en navegador con los datos reales. La barra de arriba pasa de 216 px fijos a
132 que se van al bajar: marca y tema arriba, los seis enlaces debajo.

---

## 8. Cómo trabajar

```bash
./run.sh                     # desarrollo — OJO: sobre la base REAL (TNT_DB)
./run.sh --demo              # base inventada, para probar sin riesgo
PORT=8001 ./run.sh --demo    # sin tirar la app instalada del 8000
./run_tests.sh               # toda la suite
./packaging/install.sh --no-venv   # llevar el código a la app instalada
```

- Los tests necesitan `httpx` (en `requirements-dev.txt`, que la app instalada
  no se lleva); `run_tests.sh` elige un intérprete que lo tenga.
- `/health` dice qué base sirve el servidor y si es la de demostración.
- Commits firmados como `Angus <angus@users.noreply.github.com>`, en español,
  añadiendo cada fichero por su ruta.
- El hook de pre-commit `ui-vocabulary-check` rechaza colores literales y
  `style=` nuevos en las plantillas. Nunca `--no-verify`.
- Cada decisión, una línea en `docs/QUESTIONS.md` en el momento en que se toma.
- `data/`, extractos, `.env.local`, tokens y capturas con datos reales **nunca**
  al repositorio.
- Ante un cambio de datos, copia previa:
  `cp tnt.db tnt.db.pre-<motivo>.$(date +%F-%H%M%S)`.
