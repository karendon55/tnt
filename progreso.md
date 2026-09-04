# TNT — Estado del proyecto

Documento de contexto para retomar el trabajo sin releerlo todo. Recoge sobre
todo **por qué** están hechas así las cosas y **qué trampas** ya nos han
mordido, que es lo que no se deduce leyendo el código.

Última actualización: **4 de septiembre de 2026** · 50 commits desde el 21 de abril.

---

## 1. Qué es

Aplicación local de finanzas personales para sustituir a HomeBank. Corre en
`localhost:8000`, sin servicios externos: los datos bancarios no salen del
equipo.

| | |
|---|---|
| Backend | Python 3.10 · FastAPI · Uvicorn · SQLite (sin ORM, SQL a mano) |
| Plantillas | Jinja2 renderizado en servidor |
| Interactividad | HTMX 1.9.10 (sin framework JS) |
| Estilos | Basecoat (Tailwind, estética shadcn) + capa propia de tokens |
| Gráficos | Chart.js 4.4.1 |
| Tamaño | ~5.300 líneas de Python, ~2.600 de plantillas, 77 tests |

Basecoat y Chart.js se cargan por CDN. Es deliberado: "100 % local" se refiere
a **los datos**, no a los assets.

---

## 2. Lo que ya funciona

**Importación.** Parsers para ING (XLS), CaixaBank (XLS), EuroCaja Rural (CSV) y
HomeBank (CSV, con selector de cuenta destino porque el fichero no trae IBAN).
Preview antes de confirmar y deshacer un lote entero.

**Categorización.** Reglas integradas, aprendidas y manuales. Aprende de tus
correcciones y sugiere reglas nuevas.

**Panel.** Patrimonio, KPIs del mes con variación, gasto por categoría en
barras, evolución de saldo o neto mensual (conmutable), últimos movimientos,
previsión y desglose de cuentas. Selector de mes.

**Cuentas.** CRUD, conciliación contra el saldo del banco, reglas de traspaso
externas y cuentas de inversión con valoraciones.

**Backup.** Por directorio, cifrado o plano, con contraseña protegida por clave
maestra. Restauración desde `.tnt`.

**Empaquetado.** `install.sh` instala en `~/.local/share/tnt` con icono y
lanzador. `package.sh` genera el distribuible.

---

## 3. Decisiones de diseño (el porqué)

### Los traspasos no son ingresos ni gastos
Es **la** regla estructural de la aplicación. Mover dinero entre bolsillos
propios no es actividad económica. Cuando dos movimientos se emparejan
(`transfer_id`), quedan fuera de los KPIs, del gasto por categoría y del neto.

Este error ha reaparecido tres veces con formas distintas, así que conviene
tenerlo presente:

- `DEPOSITO A PLAZO −150.000 €` contaba como gasto del mes
- `CANCELACION PLAZO +100.000 €` contaba como ingreso
- `BIZUM RECIBIDO` caía en una categoría de gasto y **restaba** en vez de sumar

Ante cualquier importe raro en los KPIs, esto es lo primero que hay que mirar.

### Un fondo no se valora sumando movimientos
Una cuenta bancaria vale lo que suman sus apuntes. Un fondo cambia de valor sin
que ocurra nada: el mercado sube o baja. Por eso las cuentas `type='investment'`
toman su saldo de la **última valoración declarada** (`account_valuations`), no
de sus movimientos.

La alternativa —anotar la revalorización como un apunte— es tentadora y está
mal: esos euros aparecerían como ingresos del mes sin que hayas ganado nada.
Los movimientos siguen registrando lo aportado y reembolsado, y la diferencia
con el valor declarado es la rentabilidad.

### En las reglas gana la específica, no la frecuente
El desempate es: **regla manual → patrón más largo → priority × hits**.

Antes ganaba la más repetida, y eso hacía que `REPSOL` (aprendida de los recibos
de luz, con 10 aciertos) se impusiera a `WAYLET` y mandara la gasolina a "Luz y
gas". Además, las reglas aprendidas **se revocan** cuando la evidencia baja del
70 %: sin eso, una regla aprendida con datos viejos sobrevivía para siempre
(había 88 obsoletas acumuladas).

### La contraseña de backup no vive en la base de datos
Estaba en `settings` en texto plano, de modo que el backup **plano** de la BD
contenía la contraseña del backup **cifrado**. Ahora se cifra con una clave
maestra en `~/.config/tnt/master.key` (permisos 600), fuera de todo lo que se
respalda.

⚠️ Si se pierde ese fichero, el backup cifrado solo se puede restaurar tecleando
la contraseña a mano. Conviene tener copia aparte.

---

## 4. Trampas conocidas

Cosas que ya han costado tiempo y volverán a morder si se olvidan.

### El repositorio no es lo que se ejecuta
El código vive en `/home/trooper/IA`, pero la aplicación corre desde
`~/.local/share/tnt`, que es **otra copia**. Editar el repo no cambia nada de lo
que el usuario ve hasta sincronizar:

```bash
./packaging/install.sh --no-venv
```

Preserva `data/` (la BD real). Sin este paso, se depuran síntomas fantasma.

### Basecoat pone `display:flex` en `.card`
Y eso **gana al `display:none`** que el navegador da a los `<dialog>` cerrados,
porque los estilos de autor mandan sobre los del agente de usuario. Como los
diálogos llevan `.card`, aparecían todos desplegados en la página. La regla
`dialog:not([open]){display:none}` lo corrige. El mismo reset anula el
`margin:auto` que centra los modales.

### Chart.js crece sin límite si el contenedor no tiene altura
Con `maintainAspectRatio:false` y un padre sin altura definida, el lienzo se
agranda en cada redibujado: en pruebas llegó a 36.000 px. **Todo gráfico va
dentro de `.chart-box` con altura fija.**

### Las tablas anchas se recortan, no se desplazan
Las tarjetas tienen `overflow:hidden`, así que una tabla que se pasa del ancho
pierde sus últimas columnas en silencio (le pasó al importe en Movimientos y al
botón en Traspasos). El patrón es `.table-scroll` + `.table-fixed` + `<colgroup>`
con anchos explícitos.

### SQLite en modo WAL y las copias
Las transacciones confirmadas viven en `tnt.db-wal` hasta el checkpoint, así que
copiar `tnt.db` a pelo puede perder los últimos movimientos. Los backups usan
`db_snapshot()`, que llama a la API de backup de SQLite. Al restaurar hay que
**borrar `-wal` y `-shm`**, o SQLite intentará aplicar el WAL viejo sobre la BD
nueva.

### Los IBAN vienen en dos formatos
Los extractos traen a veces el IBAN completo (`ES99…`, 24 caracteres) y a veces
el BBAN (20 dígitos). Comparar en crudo duplicaba cuentas al importar.
`ensure_account` normaliza y, si no encaja, compara por los últimos 20.

### Al iterar un cursor de SQLite, `fetchall()`
Reutilizar el mismo cursor dentro del bucle invalida la iteración y solo se
procesa la primera fila. Ha provocado ya un diagnóstico erróneo.

---

## 5. Datos del usuario (contexto)

9 cuentas activas, ~500.000 € de patrimonio, histórico desde enero de 2026.

- **Indexa Capital** es de tipo inversión: 60.440 € aportados, 63.334,26 € de
  valor (agosto), 8 valoraciones cargadas. Las aportaciones son anteriores al
  histórico de TNT, por eso están como saldo inicial y no como movimientos: no
  hay contrapartida bancaria con la que emparejarlas.
- **Plan pensiones Olga** sigue siendo tipo banco por decisión del usuario, con
  sus 14.650 € de aportaciones. Su valor real será otro. **No tocar.**
- **Dos depósitos de EuroCaja Rural** con reglas de traspaso en ambos sentidos
  (`deposito a plazo` / `cancelacion plazo`).

---

## 6. Pendiente

**Migrar las páginas restantes al diseño nuevo.** El panel está rehecho y todas
las páginas heredan ya los tokens (colores, radios, tipografía), pero su
*maquetación* sigue siendo la vieja. Por orden de provecho:
`/movimientos` (8 columnas es mucho; "Cuenta" repite valor en casi toda la
tabla) → `/cuentas` (la más recargada) → el resto.

**Categorías solapadas.** Conviven `Transferencias` (raíz) y
`Otros gastos | Transferencias`, con apuntes en ambas. Mismo caso que el de
"Bizum enviado" que ya se unificó; falta decidir cuál sobrevive.

**El manual está desactualizado.** `docs/Manual-TNT.docx` es de mayo: no incluye
el rediseño, el selector de mes, las cuentas de inversión ni el backup por
directorio.

**Idea sin desarrollar.** Gráfico de rentabilidad del fondo comparado con su
benchmark, que Indexa envía en el mismo correo.

---

## 7. Cómo trabajar

```bash
./run.sh                                  # desarrollo, recarga automática
./packaging/install.sh --no-venv          # sincronizar con la app instalada
~/.local/share/tnt/.venv/bin/python -m unittest discover tests
```

- Commits firmados como `Angus <angus@users.noreply.github.com>`, en español.
- Remoto: `github.com/karendon55/tnt` (privado).
- `data/`, extractos y tokens **nunca** al repositorio.
- Ante un cambio de datos, copia previa: `cp tnt.db tnt.db.pre-<motivo>.$(date +%F-%H%M%S)`.
