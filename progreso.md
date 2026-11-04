# TNT — Estado del proyecto

Documento de contexto para retomar el trabajo sin releerlo todo. Recoge el
**estado**, el **porqué** de lo que no es obvio y las **trampas** que ya han
mordido. El detalle de cada decisión está en `docs/QUESTIONS.md`; aquí solo lo
que hace falta para orientarse.

Última actualización: **3 de noviembre de 2026**. Proyecto iniciado el 21 de abril.

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
| Tamaño | 7.200 líneas de Python, 3.100 de plantillas, 610 de CSS, 423 tests |

Basecoat y Chart.js se cargan por CDN. Es deliberado: "100 % local" se refiere
a **los datos**, no a los assets.

---

## 2. Dónde está cada cosa

La documentación está repartida; esto es el mapa.

| Fichero | Para qué |
|---|---|
| `progreso.md` | este: estado, porqués y trampas |
| `docs/QUESTIONS.md` | **registro de decisiones**, una por línea (133). Leer antes de preguntar nada: lo respondido está cerrado salvo que el usuario lo reabra |
| `design-system.md` | el lenguaje visual: tokens, tipografía, qué no se hace, deuda |
| `briefs/*.md` | una por pantalla (11), con lo que vale y no vale en cada una |
| `explorations/` | los bocetos de los que salió el diseño |
| `CLAUDE.md` | convenciones del repo para el agente |
| `docs/Manual-TNT.*` | manual de usuario, **desfasado** (mayo) |

---

## 3. Lo que ya funciona

**Navegación.** Arriba, lo que se hace cada mes: Panel, Movimientos, Traspasos,
Inversiones, Presupuestos. En **Configuración**, lo de vez en cuando: Backup,
Cuentas, Categorías, Reglas, Importar, Alias y Renta. El mapa vive en
`app/navigation.py` y las URLs antiguas siguen funcionando.

**Importación.** ING y CaixaBank (XLS), EuroCaja Rural (CSV) y HomeBank (CSV,
con cuenta destino a elegir porque el fichero no trae IBAN). Preview, confirmar
y deshacer un lote entero.

**Histórico de HomeBank.** Un ejercicio entero desde `Casa.xhb`, sin tocar la
base real hasta el final: `scripts/homebank_historico.py preparar` lo carga en
una copia (con la tabla de equivalencias de categorías que revisa el usuario),
`verificar` compara la real con la copia mes a mes y `migrar` pasa lo revisado
con copia previa, comprobando que la real queda igual que la copia. La
configuración y la copia viven en `data/importacion-homebank-<año>/`, fuera de
git. 2025 está cargado.

**Categorización.** Reglas integradas, aprendidas y manuales; aprende de las
correcciones y sugiere reglas nuevas. Lo cargado del histórico de HomeBank no
enseña reglas: sus categorías salen de la tabla de equivalencias.

**Panel.** Patrimonio en grande con lo que varió en el mes que se ve, selector
de mes, banda de KPIs del mes con su variación, avisos, gasto por categoría,
evolución de saldo o neto mensual, últimos movimientos, previsión y desglose de
cuentas.

**Inversiones.** Cuentas cuyo valor marca la última valoración declarada, con
aportado, valor, rentabilidad y la curva de los dos.

**Renta** (en Configuración, `/renta`). Por ejercicio, lo que pide la
declaración del piso alquilado: ingresos por alquiler, seguro de impago, seguro
de la vivienda, IBI y comunidad, cada uno con su detalle y su total, más el total
de los dos seguros. No guarda importes: los saca de los movimientos de la
categoría «Alquiler» y de las subcategorías de «Inmueble alquilado», y suma en
céntimos exactos. Al final, «por revisar»: lo que menciona el piso sin estar en
ningún concepto. Brief en `briefs/renta.md`.

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

### Las reglas casan por palabra entera
Por subcadena, una regla corta se metía dentro de cualquier palabra: la manual
«IBI» casaba con «recIBIda» y, como las manuales ganan, una nómina recibida sin
categoría del banco acababa en Impuestos. Una palabra es una racha de letras:
números, espacios y signos la cortan, y tildes y Ñ no. Es como se aprenden las
reglas. Lo decide `rule_matching.py` y nadie más: categorizar, crear una regla,
la sugerencia de Movimientos y la carga del histórico. Lo que deja de casar
(plurales, compuestos) se queda sin categoría, a la vista; nunca en otra.

### El árbol de categorías es el de ING
Las importaciones de ING traen sus propias categorías. Lo que TNT siembra o
crean sus reglas integradas tiene que ser lo mismo, o acaba duplicado: pasó con
«Bizum enviado» y con «Transferencias». Las transferencias a otras personas van
a «Otros gastos › Transferencias» y los traspasos entre cuentas propias, a
«Movimientos excluidos › Traspaso entre cuentas». El gimnasio, a «Educación y
salud › Deporte y gimnasio». La excepción, elegida por el usuario: el transporte
público va a «Transporte › Transporte público», y lo que ING mande como «Vehículo y
transporte › Transporte público» se traduce al entrar (`_PISTAS_DEL_BANCO`).

### Tus reglas manuales mandan sobre la categoría del banco
ING trae su propia categoría en el extracto. Al importar, si una regla **manual**
casa con el movimiento, gana ella; las aprendidas no, y sin regla manda el banco.
Solo cuenta para lo que entra: lo ya importado no se toca. Antes mandaba siempre el
banco, y el alquiler llegaba cada mes como «Otros ingresos (otros)».

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
abierto, el proceso sigue con el código viejo en memoria. El instalador copia
el repo menos lo que ignora git (datos, extractos, capturas con datos reales) y
`.claude/`; la carpeta `data/` de la instalación no la toca nunca.

En cambio la **base de datos es una sola**: `.env.local` (fuera de git) apunta
`TNT_DB` a la real. Así que `./run.sh` desde el repo trabaja **sobre dinero de
verdad**: cualquier prueba de importar, restaurar o borrar lo toca. Para
experimentar, `./run.sh --demo`.

### Un `BEGIN` a mano dentro de `cursor()` rompe
La conexión va en autocommit, pero `cursor()` abre su propia transacción: un
`BEGIN` manual dentro provoca *cannot start a transaction within a
transaction*. Para lotes donde un elemento malo no debe tirar los buenos,
`savepoint()`.

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
`.table-scroll` acaba empujando la página o, dentro de un `<details>`, cortada
en el borde sin que la página se pueda desplazar. Un test exige el contenedor
en todas las plantillas.

Y si la tabla va en una rejilla, la pista es `minmax(0,1fr)`: una `1fr` a secas
no baja del ancho mínimo de su contenido, y una tabla así empujó el panel a
598 px en una pantalla de 375. Se comprueba midiendo, no mirando:
`scrollWidth` igual a `clientWidth`.

### Un JOIN de `transactions` consigo misma necesita su índice
SQLite usa un índice por tabla en cada paso del JOIN. La búsqueda de
duplicados iba por el de cuenta y comparaba cada movimiento con todos los de
su cuenta: crecía con el cuadrado de los datos (290 ms con 2.749). Acotar las
fechas en el JOIN no ayudó (763 ms): seguía yendo por la cuenta. Lo arregló un
índice que casa con sus igualdades, `(account_id, amount)`: 7 ms. Se comprueba
con `EXPLAIN QUERY PLAN`, y un test lo vigila.

### SQLite en modo WAL y las copias
Lo confirmado vive en `tnt.db-wal` hasta el checkpoint: copiar `tnt.db` a pelo
pierde lo último. Los backups usan `db_snapshot()`. Al restaurar hay que borrar
`-wal` y `-shm`, o SQLite aplicará el WAL viejo sobre la base nueva.

### Los IBAN vienen en dos formatos
IBAN completo (`ES99…`, 24 caracteres) o BBAN (20 dígitos). Comparar en crudo
duplicaba cuentas al importar; `ensure_account` normaliza y, si no encaja,
compara por los últimos 20.

### Las de los primeros meses, siguen vigentes
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

### Las reglas no distinguen los recibos de un piso de los del otro
El IBI de los dos pisos llega como «Recibo Ayuntamiento de Madrid», y los seguros
con el nombre de la aseguradora: las reglas, que solo miran la descripción, los
meten donde caiga (normalmente «Pago de impuestos» o «Seguros del hogar»). Los del
piso alquilado tienen que pasar a mano a su subcategoría de «Inmueble alquilado».
Para eso está «por revisar» en la Renta: los encuentra por la nota del banco.
Sin esa nota, no hay forma de que aparezcan.

### Al iterar un cursor de SQLite, `fetchall()`
Reutilizar el mismo cursor dentro del bucle invalida la iteración y solo se
procesa la primera fila.

---

## 6. Datos del usuario (contexto)

2.749 movimientos de enero de 2025 a septiembre de 2026, en 9 cuentas activas.
Los 1.641 de 2025 vienen del histórico de HomeBank, migrado el 8/10/2026; copia
de la base de justo antes en `data/importacion-homebank-2025/`.

- **Indexa Capital**, de tipo inversión: 60.740 € aportados, lo mismo que dice
  Indexa, y 63.759,24 € de valor en septiembre. Lo aportado antes de 2025 es
  saldo inicial; lo de después son traspasos emparejados desde CaixaBank. Tiene
  la valoración de cada cierre de mes desde diciembre de 2024.
- **Plan pensiones Olga** sigue de tipo banco por decisión del usuario, con sus
  14.650 € aportados; su valor real será otro. **No tocar.**
- **Dos depósitos de EuroCaja Rural** (anual al 2,30 %, vence 20/08/2027; nueve
  meses al 3,00 %, vence 14/02/2027), con reglas de traspaso en los dos
  sentidos.
- **Dos pisos, uno alquilado.** Sus gastos de 2026 (impago, seguro de la
  vivienda, tres plazos de IBI y la comunidad: 9 movimientos) se pasaron el
  7/10/2026 a las subcategorías de «Inmueble alquilado»; los del otro piso siguen
  donde estaban. El nombre del piso y la palabra a ignorar (la tasa de basuras,
  que no cuenta) están en los ajustes de la Renta, en la base, no en el código.
  Copia previa: `tnt.db.pre-renta.2026-10-07-111648`.

---

## 7. Pendiente

Comprobado contra el código y los datos el 3 de noviembre de 2026.

### Necesita una decisión del usuario

Nada: todo lo pendiente se puede hacer sin preguntar, o no es código.

### Se puede hacer sin decisiones

- **Manual.** Es de mayo: no recoge el rediseño, la navegación nueva, las
  inversiones, el modo demostración, el móvil ni la Renta. Lo más largo de la
  lista.
- **Ficheros sobre el tope blando de 350 líneas**, ninguno sobre el duro de 500:
  `analytics.py` (455), `backup.py` (426), `transactions.py` (409),
  `import_page.py` (400), `db.py` (374), `categorizer.py` (369),
  `tests/test_analytics.py` (398) y `tests/test_homebank_historico.py` (379). Se
  parten cuando toque cambiarlos, empezando por `analytics.py`.

### Recurrente (no es código)

- **El cuarto plazo del IBI** del piso alquilado no llegó en octubre. Cuando llegue,
  como «Recibo Ayuntamiento de Madrid», irá a «Pago de impuestos»: saldrá en «por
  revisar» de la Renta y hay que pasarlo a «Inmueble alquilado › IBI». Igual cada
  año con los seguros, al renovarse.
- **Cada mes:** importar los extractos y meter la valoración de Indexa del mes
  anterior; el formulario ya propone el último día de ese mes.
- **Depósitos:** el de nueve meses vence el 14/02/2027 y el anual el 20/08/2027.
  Sus reglas reflejan la cancelación por el importe; uno nuevo de otro importe
  necesita su propia cuenta y sus dos reglas.

### Ideas sin desarrollar

- Comparar la rentabilidad del fondo con su benchmark, que Indexa envía en el
  mismo correo.
- Años de HomeBank anteriores a 2025: el mismo programa, con otra
  configuración y su tabla de equivalencias.

### Resuelto en noviembre

- **3/11** — Al importar, tus reglas manuales mandan sobre la categoría del banco.
  El alquiler de octubre, a «Alquiler», con su regla para los próximos, y 22
  movimientos de ING que no seguían tus reglas, corregidos. Copia previa junto a la
  base.
- **3/11** — La comunidad del piso alquilado del 4.º trimestre, a «Inmueble alquilado ›
  Comunidad», con dos reglas manuales (una por cada formato del recibo) para que las
  próximas vayan solas. La Renta de 2026 no tiene nada por revisar.
- **3/11** — Sin categorías repetidas: el transporte público, todo en «Transporte»
  (31), y el gimnasio, todo en «Educación y salud» (22), con tus reglas apuntando ahí.
- **3/11** — Tercera referencia visual bloqueada en `design-system.md`: Mercury, para
  las tablas y listas de dinero (capturas y notas en `explorations/sistema-refs/`).
- **3/11** — El panel e Inversiones llevan los céntimos en voladita en sus cifras grandes.
- **3/11** — Cuentas, en filas de dos líneas: nombre y subtítulo, con el saldo a la derecha;
  en el móvil, cuenta y saldo actual a la vista. La tercera referencia ya está en las tres
  pantallas previstas.
- **3/11** — Fuera las tres copias sueltas de la base de ese día (a la papelera).
- **4/11** — La Renta abierta dos veces a la vez la primera vez ya no falla: en modo WAL no
  duplicaba, pero la segunda daba «database is locked». La creación pide la escritura
  desde el principio (`cursor(inmediata=True)`), y un índice único impide dos categorías
  principales con el mismo nombre.

### Resuelto en octubre

- **1/10** — Las reglas de los depósitos distinguen cada uno por su importe exacto.
- **2/10** — La valoración del fondo propone el cierre del mes anterior; la de
  septiembre pasó del 01/10 al 30/09.
- **2/10** — La línea bajo el patrimonio es su variación en el mes que se ve, y
  cuadra con la curva.
- **2/10** — Las trece pantallas caben a 375 px: todas las tablas en
  `.table-scroll` y la barra del móvil en dos filas, sin fijar.
- **7/10** — Sección Renta en Configuración, con los 9 movimientos de 2026 del
  piso alquilado ya clasificados.
- **8/10** — Histórico de HomeBank de 2025 en la base real, pasando por una base
  de prueba: 2026 queda idéntico salvo las dos aportaciones al fondo, que pasan
  a ser traspasos. El panel, los movimientos y la Renta tienen ya 2025.
- **8/10** — Fuera `HANDOFF.md`. «Transferencias» unificada con el árbol de ING:
  97 traspasos a «Movimientos excluidos › Traspaso entre cuentas» y la paga
  mensual (28) a «Otros gastos › Transferencias», con su regla manual; saldos,
  ingresos y gastos idénticos. Copia previa junto a la base.
- **8/10** — El panel busca los duplicados por índice: de 0,32 s a 0,03 s, con
  los mismos avisos.
- **8/10** — Clasificados los 13 movimientos de 2025 que llegaron de HomeBank sin
  categoría: no queda ninguno sin ella.
- **8/10** — Un 0,0 % en los indicadores del panel sale «= 0,0 %» en neutro, no
  «▲» en verde. Fuera la copia de `download.csv` de la app instalada.
- **8/10** — Las reglas de categoría casan por palabra entera, no por
  subcadena, en los cuatro sitios que las usan. Un patrón en blanco avisa, al
  crear y al editar; antes, al editar, se guardaba una regla que casaba con todo.
- **8/10** — Borrada la regla manual «IBI»: por palabra entera no casaba con
  ningún movimiento (los recibos llegan como «Recibo Ayuntamiento de Madrid») y
  por subcadena solo casaba dentro de «recibida». Copia previa junto a la base.
- **8/10** — Fuera las siete copias sueltas de la base (a la papelera, con la base
  de prueba) y el worktree de la sesión de las reglas, ya mezclada en `main`.

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
