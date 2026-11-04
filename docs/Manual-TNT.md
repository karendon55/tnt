# 1. ¿Qué es TNT?

TNT — Tus Números Tranquilos — es una aplicación local de finanzas personales. Nació como sustituto de HomeBank: importa los extractos de tu banco, categoriza los movimientos, te enseña cuánto tienes y cómo ha ido el mes, y vive entera en tu ordenador.

TNT no se conecta a ningún servicio externo: no hay APIs bancarias, ni nube, ni telemetría. Toda la información está en un único fichero SQLite que tú controlas y respaldas. La interfaz es web (un servidor local en `127.0.0.1:8000`), pero no se expone fuera del ordenador.

## Filosofía

- **Local:** tus datos viven solo en tu disco.
- **Reversible:** un lote importado se deshace de un clic, una restauración deja copia de lo anterior y los alias no tocan nada de la base.
- **Sin ataduras:** exportas a CSV cuando quieras y la base es SQLite estándar.
- **Tranquila:** «papel en oscuro». Fondo casi negro, cifras en serif, filetes finos en vez de tarjetas, y el rojo solo para la marca, la acción principal y lo negativo. Si lo prefieres, tema claro con el botón de la luna, arriba a la derecha.

# 2. Requisitos

## Sistema operativo

TNT está probado en Linux (Ubuntu 22.04 y 24.04). Debe funcionar en otras distribuciones modernas con escritorio: solo necesita Python y un navegador.

## Software

- **Python 3.10 o superior.**
- **Un navegador moderno** (Firefox, Chromium, Chrome…).
- **python3-venv:** el paquete del sistema que crea entornos virtuales. En Debian y Ubuntu no viene con Python.

```
sudo apt install python3-venv
# o, si tu Python es 3.10 concretamente:
sudo apt install python3.10-venv
```

- **gnumeric:** solo si vas a importar los `.xls` antiguos de ING. Trae `ssconvert`, que TNT usa para leerlos.

```
sudo apt install gnumeric
```

## Dependencias de Python

Están en `requirements.txt` y el instalador las pone solas:

- **fastapi** · el servidor web.
- **uvicorn[standard]** · lo que lo sirve.
- **jinja2** · las páginas.
- **python-multipart** · subir ficheros (extractos y backups).
- **openpyxl** · leer el XLS de CaixaBank.
- **cryptography** · el backup cifrado.

# 3. Instalación

## 3.1 Como aplicación de escritorio (recomendada)

Así TNT queda en el menú de aplicaciones, con su icono del rayo, y con un comando `tnt-launcher` para la terminal. No necesita permisos de administrador. Desde la carpeta del proyecto:

```
./packaging/install.sh
```

El instalador:

- Comprueba que tienes Python 3.10 o superior y el módulo `ensurepip` (sin él no se puede crear el entorno virtual).
- Copia el código a `~/.local/share/tnt/`. Solo lo que es código: deja fuera tus datos, los extractos y las capturas, y no toca nunca la carpeta `data/` de la instalación.
- Crea el entorno virtual `.venv/` e instala las dependencias.
- Instala el icono, el lanzador `~/.local/bin/tnt-launcher` y la entrada del menú.

### Si falla con «ensurepip is not available»

A tu Python le falta el paquete `python3-venv`. Instálalo y vuelve a lanzar el instalador:

```
sudo apt install python3-venv
# si ese paquete no existe, prueba con tu versión exacta:
sudo apt install python3.10-venv
./packaging/install.sh
```

El instalador lo detecta al principio y se para antes de tocar nada. Si no quieres usar un entorno virtual, la opción `--no-venv` lo salta.

### Opciones del instalador

- `--prefix=RUTA` · otra raíz (por defecto `$HOME/.local`), por ejemplo un pendrive.
- `--no-venv` · usa el `python3` del sistema, que ya debe tener las dependencias.

Si tras instalar no ves TNT en el menú, comprueba que `~/.local/bin` está en tu `PATH`:

```
export PATH="$HOME/.local/bin:$PATH"
```

Añádelo a tu `~/.bashrc` o `~/.zshrc` para que sea permanente.

## 3.2 Actualizar TNT

Vuelve a lanzar `./packaging/install.sh` desde la carpeta del proyecto. Tus movimientos, categorías, reglas y ajustes no se tocan. Si TNT estaba abierto, el instalador lo avisa: ciérralo y vuelve a abrirlo para ver la versión nueva.

## 3.3 Desde el código (modo desarrollador)

Para probar TNT desde la carpeta del repositorio, sin instalarlo:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
```

Arranca con recarga automática: los cambios en el código se ven al momento. Es para desarrollo, no para el día a día.

# 4. Arrancar TNT

## Desde el menú de aplicaciones

Busca «TNT» en el menú y pulsa el icono del rayo. El lanzador arranca el servidor si no estaba ya, espera a que responda y abre tu navegador en `http://127.0.0.1:8000`. Si ya estaba abierto, solo abre la pestaña.

## Desde la terminal

```
tnt-launcher
```

Hace lo mismo que el menú.

## Desde la carpeta del proyecto (modo desarrollador)

```
./run.sh
```

Deja la terminal enseñando lo que hace el servidor. Para pararlo, Ctrl+C.

## Variables del lanzador

- `TNT_PORT` · puerto (por defecto 8000).
- `TNT_HOST` · interfaz (por defecto `127.0.0.1`; no la cambies si no sabes lo que haces).
- `TNT_HOME` · dónde está instalado TNT (el lanzador lo sabe solo).
- `TNT_PYTHON` · el intérprete de Python que usar.

## Modo demostración

Para probar TNT sin tocar tus datos, levántalo sobre una base inventada. La primera vez hay que crearla:

```
TNT_DB=$PWD/data/tnt-demo.db .venv/bin/python scripts/make_demo_db.py
./run.sh --demo
```

En la barra aparece la píldora «Datos de demostración». En este modo el backup está bloqueado, para que una copia de la base inventada no pise nunca tus copias buenas. Para tenerlo a la vez que la app normal, en otro puerto:

```
PORT=8001 ./run.sh --demo
```

# 5. Funcionalidades

Este capítulo recorre la aplicación en el orden de su barra de arriba.

## 5.1 La barra de arriba y Configuración

Arriba está lo que se mira a menudo: **Panel**, **Movimientos**, **Traspasos**, **Inversiones** y **Presupuestos**. Lo que se toca de vez en cuando vive en **Configuración**, con su propia barra: **Backup**, **Cuentas**, **Categorías**, **Reglas**, **Importar**, **Alias** y **Renta**.

El botón de la luna, arriba a la derecha, cambia entre tema oscuro y claro, y TNT lo recuerda.

## 5.2 Panel

Ruta: `/` (la portada).

El panel responde, sin bajar, a tres preguntas: cuánto hay, cómo ha ido el mes y si algo pide atención.

- **Patrimonio total:** la suma de tus cuentas activas, en grande. Debajo, cuánto ha variado en el mes que estás viendo y cuántas cuentas cuentan. Los fondos cuentan por su última valoración (ver Inversiones).
- **El mes:** con las flechas o el selector eliges otro. Si el mes actual aún no tiene datos, el panel enseña el último que los tenga y lo avisa con la píldora «último mes con datos».
- **Ingresos, gastos y neto del mes:** cada uno con su variación frente al mes anterior. Gastar más sale con flecha arriba y en rojo; gastar menos, abajo y en verde. Un mes igual que el anterior sale «= 0,0 %», sin color. Los traspasos entre tus cuentas no cuentan como ingreso ni como gasto.
- **Avisos:** posibles duplicados (dos movimientos iguales en la misma cuenta a tres días o menos) y subidas de precio de más del 15 % en un recibo que se repite.
- **A dónde fue el dinero:** el gasto del mes por categoría, con su variación frente al mes anterior.
- **Evolución del saldo:** la curva del saldo al cierre de cada mes, o el neto de cada mes con el botón «Neto mensual».
- **Últimos movimientos, previsión del mes siguiente y desglose por cuenta.** La previsión parte del saldo actual y suma lo que se repite (recibos y cobros) y una estimación del gasto variable: la media de los tres últimos meses.

Las cifras grandes llevan los céntimos y el «€» en pequeño, arriba: «1.234,⁵⁶ €». Se leen igual.

## 5.3 Movimientos

Ruta: `/movimientos`.

La lista de todos tus movimientos, del más reciente al más antiguo, por páginas.

- **Filtros:** «Buscar» (en la descripción y el memo, sin distinguir mayúsculas), cuenta, categoría (incluida «Sin categoría») y un rango de fechas. «Limpiar» los quita.
- **Cambiar la categoría** desde la propia fila, con su selector. Si la descripción tiene palabras que se repiten en otros movimientos, TNT te propone convertir tu decisión en una regla para los próximos.
- **El memo** se edita en el sitio, sin recargar la página.
- **Editar y borrar** cada movimiento, con los iconos del final de la fila.
- **Nuevo movimiento:** para un gasto en efectivo o un ajuste. El importe en negativo es un gasto.
- **Exportar CSV:** descarga lo que tengas filtrado.

Las descripciones se ven con sus alias (ver Alias); la base guarda siempre la original del banco.

## 5.4 Traspasos

Ruta: `/traspasos`.

Un traspaso entre tus cuentas es una salida en una y una entrada en otra. Emparejados, no cuentan como gasto ni como ingreso. La pantalla tiene tres bloques:

- **Emparejados:** todos los pares, con «Desemparejar».
- **Sugerencias:** posibles pares (importes opuestos, cuentas distintas, a pocos días y los dos sueltos), con «Emparejar».
- **Emparejar a mano:** dos selectores para lo que las sugerencias no encuentran.

Si el dinero va a una cuenta cuyo extracto no importas (un fondo, un depósito), una regla de transferencia externa crea el movimiento de llegada y los empareja sola (ver Reglas).

## 5.5 Inversiones

Ruta: `/inversiones`.

Un fondo cambia de valor sin que haya movimientos, así que su saldo no sale de sumar aportaciones: lo marca el último valor que declares aquí, con el informe de la entidad. Cada cuenta de tipo «Inversión» tiene su hoja:

- **Aportado neto:** lo que has puesto menos lo que has sacado.
- **Valor actual:** la última valoración, con su fecha.
- **Rentabilidad:** valor menos aportado, en euros y en porcentaje.
- **Guardar valoración:** la fecha del informe (propone el último día del mes anterior), el valor y una nota.
- **La curva:** el valor en tinta y lo aportado en punteado. El hueco entre las dos es tu rentabilidad.
- **El histórico de valoraciones**, en su desplegable, con un botón para borrar cada una.

La rentabilidad no es un ingreso: no cambia los ingresos y gastos del panel, aunque sí su patrimonio.

## 5.6 Presupuestos

Ruta: `/presupuestos`.

Un límite mensual por categoría, con su barra: avisa a partir del 80 % y, al pasarse, sale la píldora «Highway to Hell». Arriba, el total presupuestado frente a lo gastado. Se crean, cambian y borran desde la misma pantalla.

## 5.7 Importar extractos

Ruta: Configuración › Importar (`/importar`).

Sube uno o varios extractos y TNT reconoce el banco por su formato:

- **ING:** el XLS antiguo, que TNT convierte con `ssconvert` (gnumeric).
- **CaixaBank:** el XLS nativo.
- **EuroCaja Rural:** el CSV de su banca online (`download.csv`).

«¿Cómo obtener el extracto?» lo explica para cada banco.

### Vista previa antes de confirmar

Antes de escribir nada, TNT enseña por cada fichero cuántos movimientos son nuevos, cuántos ya estaban (se saltan) y una muestra. Confirmas con un botón. La vista previa caduca a los 10 minutos.

### Qué categoría recibe cada movimiento

- Si **una regla manual tuya** casa con la descripción, manda ella.
- Si no, **la categoría que trae el banco** (ING la trae), si la trae.
- Lo que llegue sin categoría lo intentan **el resto de reglas**, las aprendidas y las integradas.

Al acabar, TNT vuelve a aprender reglas de todo lo categorizado. La pantalla de resultado dice cuántos categorizó el banco y cuántos las reglas.

### Lotes y «Deshacer»

Cada importación es un lote. En «Lotes anteriores» (`/importar/lotes`) puedes deshacer uno entero: sus movimientos desaparecen de golpe, en una sola operación.

### 5.7.1 Importar movimientos de HomeBank (CSV)

En la misma pantalla, «Importar histórico de HomeBank» trae movimientos exportados de HomeBank sin volver a pasar por los extractos del banco. Para traer un año entero con sus categorías revisadas y los saldos cuadrados, hay una herramienta más completa: ver el capítulo 6.

- **En HomeBank:** Archivo → Exportar → Movimientos en CSV. El fichero tiene la cabecera `date;payment;info;payee;memo;amount;category;tags`. Si tienes varias cuentas, exporta una a una.
- **En TNT:** elige la cuenta destino (el CSV no trae IBAN), sube el fichero y confirma en la vista previa.

Reimportar el mismo fichero no duplica nada: cada movimiento lleva una huella (cuenta, fecha, importe y descripción). La categoría de HomeBank se trata como la del banco: si no existe en TNT se crea, y tus reglas manuales le ganan. El CSV no trae saldos: si el saldo inicial de la cuenta no es el bueno, ajústalo en Cuentas. Las etiquetas y la forma de pago se guardan en el memo.

## 5.8 Cuentas y conciliación

Ruta: Configuración › Cuentas (`/cuentas`).

Cada cuenta va en una fila de dos líneas: el nombre y, debajo, el banco, el tipo y los cuatro últimos dígitos del IBAN, cada uno solo si el nombre no lo dice ya. A la derecha, el saldo inicial, el número de movimientos, el saldo actual y su conciliación.

- **Nueva cuenta**, con su nombre, banco, IBAN, tipo (banco, efectivo, tarjeta o inversión) y saldo inicial.
- **Editar:** el lápiz. El IBAN completo se ve aquí.
- **Archivar** una cuenta que ya no usas: sus movimientos se quedan, pero deja de sumar al patrimonio. Se restaura desde «Archivadas».
- **Conciliar:** escribes el saldo que dice el banco en una fecha y TNT te dice si cuadra con el suyo o por cuánto difiere. Cada conciliación queda en su historial, y la fila dice, por ejemplo, «cuadra, hace 35 d», «difiere −12,34 €» o «sin conciliar». Una diferencia suele ser un movimiento sin importar o uno repetido.

El saldo actual es el saldo inicial más los movimientos; el de una cuenta de inversión, su última valoración.

## 5.9 Categorías y evolución

Ruta: Configuración › Categorías (`/categorias`).

El árbol de categorías, de gasto y de ingreso, con sus subcategorías. Puedes crear, renombrar, mover una subcategoría a otra principal y borrar las que no tengan ni movimientos ni subcategorías. No puede haber dos categorías principales con el mismo nombre.

TNT sigue el árbol que traen las importaciones de ING. Así, las transferencias a otras personas van a «Otros gastos › Transferencias» y los traspasos entre tus cuentas a «Movimientos excluidos › Traspaso entre cuentas».

### Evolución por categoría

«Ver evolución» (`/categorias/evolucion`) dibuja el gasto o el ingreso de las categorías mes a mes: eliges gastos o ingresos, el número de meses y cuántas categorías ver (el resto se junta en «Otros»). Sirve para ver si un recibo va subiendo o si una categoría se dispara.

## 5.10 Reglas

Ruta: Configuración › Reglas (`/reglas`).

TNT categoriza sin servicios externos ni inteligencia artificial: cada regla es un patrón y una categoría. Hay tres clases:

- **Manuales:** las que escribes tú. Siempre ganan, incluso a la categoría que trae el banco al importar.
- **Aprendidas:** TNT las saca de cómo tienes categorizado lo que ya hay. Se rehacen en cada importación, y desaparecen si dejas de categorizar así.
- **Integradas:** patrones bancarios comunes (Bizum, nómina, comisiones…).

El patrón se busca **por palabras enteras**: «IBI» casa con «Recibo IBI», no con «Transferencia recibida». Si casan varias, gana la manual; luego, el patrón más largo.

- **Nueva regla de categorización:** patrón, categoría y prioridad. «Crear y aplicar» la aplica también a lo que ya esté sin categoría (no toca lo que ya tiene).
- **Reentrenar:** vuelve a aprender las reglas y las aplica a lo que esté sin categoría.

### Transferencias externas

Una regla de transferencia externa dice: cuando salga un movimiento con este patrón (de esta cuenta, si la eliges), crea su llegada en esta otra y empareja los dos como traspaso. Sirve para aportaciones a un fondo, a un plan de pensiones o a un depósito, cuyos extractos no importas. El «importe exacto» es opcional: distingue dos reglas con la misma descripción, como dos depósitos que solo se diferencian en el importe.

## 5.11 Alias de descripciones

Ruta: Configuración › Alias (`/alias`).

Las descripciones del banco vienen sucias, del tipo «COMPRA EN DEMO FRUTERIAS S.L. MADRID». Un alias hace que se vean limpias, como «Demo Fruterías».

- **Patrón:** el trozo de descripción que se busca, en mayúsculas.
- **Alias:** lo que se enseña cuando casa.

El alias es solo para la vista: la base guarda la descripción original, y borrar un alias la devuelve tal cual.

## 5.12 Backup y restauración

Ruta: Configuración › Backup (`/backup`).

### Copias en tus carpetas

En «Editar destinos» pones las carpetas donde quieres las copias (una carpeta de Dropbox, otra de documentos…). Cada destino puede ir **cifrado** o **sin cifrar**. La contraseña de un destino cifrado se guarda protegida con una clave maestra que vive solo en tu ordenador (`~/.config/tnt/master.key`), nunca en la base.

- **Hacer backup ahora** copia a todos los destinos; «Backup ahora» en cada uno, solo a ese.
- La copia es íntegra aunque TNT esté escribiendo en ese momento, y sustituye a la anterior.

### Backup cifrado para descargar

Escribe una contraseña (8 caracteres como mínimo) y TNT te descarga un fichero `tnt-backup-AAAAMMDD-HHMMSS.tnt`. Va cifrado con Fernet (AES con HMAC-SHA256) y una clave derivada de tu contraseña con PBKDF2-HMAC-SHA256, 480.000 iteraciones y sal aleatoria.

Si pierdes la contraseña, el contenido es irrecuperable: TNT no la guarda en ningún sitio.

### Restaurar

En «Restaurar desde backup cifrado» subes el `.tnt` y su contraseña. Antes de sustituir tu base, TNT guarda la actual al lado, como `tnt.db.before-restore-XXXXXXXX`: si algo no te convence, esa es tu vuelta atrás.

Después de restaurar, cierra TNT y vuelve a abrirlo.

## 5.13 Renta

Ruta: Configuración › Renta (`/renta`).

Lo que pide la declaración de la Renta de un piso alquilado, por ejercicio:

- **Ingresos por alquiler**, de la categoría «Alquiler».
- **Seguro de impago, seguro de la vivienda, IBI y comunidad**, de las subcategorías de «Inmueble alquilado».

Cada concepto tiene su detalle, movimiento a movimiento, y su total, con enlaces a Movimientos y a su CSV, más el total de los dos seguros. No guarda importes: los saca de tus movimientos cada vez, en céntimos exactos. Las devoluciones restan.

- **Ejercicio:** de enero a junio propone el año anterior, que es el que se declara; luego, el actual.
- **Por revisar:** lo del ejercicio que menciona el piso, o cuelga de «Inmueble alquilado», sin estar en ningún concepto. Lo que no cuente (una tasa que no se declara, por ejemplo) se saca con las palabras a ignorar.
- **Ajustes de la revisión:** cómo aparece el piso en tus notas y las palabras a ignorar.

La primera vez que se abre, crea sus categorías. Si borras una, la sección lo avisa y ofrece «Volver a crearla». Con reglas manuales (Reglas), sus recibos llegan solos a su sitio al importar.

## 5.14 En pantallas pequeñas

TNT se adapta a ventanas estrechas, hasta el ancho de un móvil:

- La barra de arriba pasa a dos filas.
- Las tablas anchas se deslizan dentro de su caja, sin mover la página.
- Las columnas menos necesarias se ocultan antes que los importes.

Para usarlo desde el móvil, ver las preguntas frecuentes.

# 6. HomeBank

## 6.1 Traer un año entero desde Casa.xhb (avanzado)

Para traer un ejercicio completo de HomeBank con sus categorías adaptadas a TNT y los saldos cuadrados al céntimo, hay un programa de consola que nunca toca tu base hasta el final:

```
.venv/bin/python scripts/homebank_historico.py preparar
.venv/bin/python scripts/homebank_historico.py verificar
.venv/bin/python scripts/homebank_historico.py migrar
```

- **preparar** copia tu base en una base de prueba y carga allí el año. Usa una tabla de equivalencias entre las categorías de HomeBank y las de TNT, que revisas tú, y no crea categorías. Si HomeBank no cuadra con el banco a fin de año, la diferencia queda como un movimiento visible, «Discrepancia en la importación». Con `--rehacer` se empieza de cero.
- **verificar** compara tu base con la de prueba mes a mes (saldos, patrimonio, ingresos, gastos y categorías) y dice exactamente qué cambiaría.
- **migrar** hace una copia de tu base y pasa lo revisado. Antes de confirmar comprueba que tu base queda igual que la de prueba; si no, no escribe nada.

La configuración (dónde está el fichero `.xhb`, qué cuenta es cada una…) vive en `data/importacion-homebank-<año>/config.json`, fuera de git, porque lleva datos tuyos. Lo cargado así no enseña reglas: sus categorías vienen de la tabla, no de cómo categorizas hoy.

Mientras revisas, puedes abrir la base de prueba en modo demostración y en otro puerto:

```
TNT_DB=<ruta de la base de prueba> TNT_DEMO=1 PORT=8002 ./run.sh
```

## 6.2 El flujo mensual antiguo

Antes de TNT, la carga mensual en HomeBank la preparaba el agente Angus. Queda como referencia mientras HomeBank siga en uso:

- Exportar los extractos del banco como `movements-DDMMYYYY.xls`.
- Convertirlos a CSV: `libreoffice --headless --convert-to csv …`.
- Categorizar con `categorias.csv` y las correcciones acumuladas.
- Generar `Carga_Homebank_MMMYYYY.csv` (separador `;`, fecha DD/MM/AAAA, importe con coma decimal).

# 7. Llevar TNT a otro PC

## 7.1 En tu PC: empaquetar

```
./packaging/package.sh                # versión automática: AAAAMMDD-commit
./packaging/package.sh 1.0.0          # versión a mano
```

Deja dos ficheros en `packaging/dist/`:

- `tnt-<versión>.tar.gz` · el paquete.
- `tnt-<versión>.sha256` · su huella, para comprobar que llega entero.

## 7.2 En el PC de destino: instalar

Antes, Python 3.10 o superior y el paquete `python3-venv`:

```
sudo apt install python3-venv
tar -xzf tnt-<versión>.tar.gz
cd tnt-<versión>
./packaging/install.sh
```

Y ya está: el instalador crea el entorno, instala las dependencias y registra la app en el menú.

## 7.3 Comprobar el paquete (opcional)

```
sha256sum -c tnt-<versión>.sha256
```

## 7.4 Qué lleva el paquete

Solo lo que sigue git: el código, los iconos, los scripts de instalación y la documentación. No lleva:

- **Tus datos:** ni la carpeta `data/` (la base y cualquier carpeta de importación) ni tus ajustes locales (`.env.local`).
- **Extractos:** ni los `.xls` y `.csv` de los bancos, ni las cargas de HomeBank.
- **Capturas de la app con tus datos**, que se quedan solo en tu ordenador.
- **Lo de tu máquina:** ni `.git/`, ni el entorno `.venv/`, ni los registros (`logs/`).

Cada persona empieza con su base de datos en blanco.

# 8. Desinstalación

## 8.1 Conservando tu base de datos (lo normal)

```
~/.local/share/tnt/packaging/uninstall.sh
```

Quita el lanzador, la entrada del menú, los iconos y el código, pero deja `~/.local/share/tnt/data/tnt.db`: la puedes mover o reutilizar si vuelves a instalar.

## 8.2 Borrando todo, también la base

```
~/.local/share/tnt/packaging/uninstall.sh --purge
```

Atención: `--purge` borra también la carpeta `data/`. Antes, descarga un backup cifrado si tu base tiene algo que quieras conservar.

## 8.3 A mano

Si el script falla:

```
rm -rf ~/.local/share/tnt
rm -f ~/.local/bin/tnt-launcher ~/.local/bin/tnt
rm -f ~/.local/share/applications/tnt.desktop
find ~/.local/share/icons/hicolor -name 'tnt.*' -delete
update-desktop-database ~/.local/share/applications 2>/dev/null
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null
```

# 9. Preguntas frecuentes

## La instalación falla con «ensurepip is not available». ¿Qué hago?

A tu Python le falta el paquete `python3-venv`. Instálalo (`sudo apt install python3-venv`, o `python3.10-venv` con tu versión exacta) y vuelve a lanzar `./packaging/install.sh`. El instalador lo detecta al principio y se para antes de tocar nada.

## ¿TNT envía mis datos a algún sitio?

No. TNT no se conecta a ningún servicio externo. Todo pasa entre tu navegador y el servidor que corre en tu propio ordenador (`127.0.0.1`), y TNT no escucha en ninguna otra interfaz.

## ¿Dónde está mi base de datos?

En `~/.local/share/tnt/data/tnt.db` si instalaste con el instalador. Es un fichero SQLite normal que puedes abrir con cualquier visor, como DB Browser for SQLite, si quieres curiosear.

## ¿Qué bancos puedo importar?

ING y CaixaBank (sus XLS) y EuroCaja Rural (su CSV), además de los CSV de HomeBank. Otro banco necesita un lector nuevo en `app/importers/`, con sus funciones `matches` y `parse`, registrado en `dispatcher.py`. Mientras tanto, si ese banco exporta para HomeBank, puedes pasar por la importación de HomeBank.

## ¿Puedo traer mis movimientos antiguos de HomeBank?

Sí, de dos formas: un CSV por cuenta desde Importar (sección 5.7.1), o un año entero con sus categorías revisadas y los saldos cuadrados (capítulo 6).

## He cambiado una categoría y los movimientos parecidos no han cambiado

Es así a propósito: cambiar la categoría de un movimiento solo toca ese. Para los parecidos, acepta la regla que TNT te propone, o crea una en Reglas con «Crear y aplicar».

## Un movimiento de ING no coge mi regla

Si la regla es manual, al importar gana a la categoría que trae ING. Si ya estaba importado antes de crearla, no se toca: cámbialo desde Movimientos. Recuerda que el patrón se busca por palabras enteras.

## Mis cuentas no cuadran con el banco. ¿Qué hago?

Concilia la cuenta en Cuentas: escribe el saldo del banco en una fecha y TNT te dirá por cuánto difiere y en qué sentido. Suele ser un movimiento que no se importó o uno importado dos veces; los posibles duplicados también salen en los avisos del panel.

## ¿Qué hago si olvido la contraseña del backup cifrado?

Nada: es irrecuperable por diseño, y esa es la garantía de que el fichero es seguro. Guárdala en un gestor de contraseñas.

## ¿Puedo abrir TNT en dos ventanas a la vez?

Sí, las dos ven la misma base. Si cambias algo en una, recarga la otra para verlo.

## ¿Puedo usar TNT desde el móvil?

La pantalla se adapta al ancho de un móvil, pero TNT solo atiende a tu propio ordenador. Para entrar desde el móvil haría falta un túnel SSH (`ssh -L 8000:127.0.0.1:8000 …`). TNT está pensado para usarse en el ordenador.

## ¿Cómo cambio el puerto?

Con la variable `TNT_PORT` al arrancar el lanzador: `TNT_PORT=9000 tnt-launcher`.

## ¿Pierdo los datos si actualizo TNT?

No. El instalador nunca toca la carpeta `data/` de la instalación: tus movimientos, categorías y ajustes siguen ahí.

## ¿Puedo tener varias bases de datos?

No oficialmente. Una opción casera es instalar otra copia en otra ruta con `--prefix=` y arrancar cada una en un puerto distinto. Para probar sin riesgo, el modo demostración (capítulo 4) ya usa una base aparte.

## Algo falla al arrancar. ¿Dónde miro?

En los registros: `~/.local/share/tnt/logs/tnt-AAAAMMDD.log`. Si arrancaste con `./run.sh`, salen directamente en la terminal.

# Apéndice · Comandos rápidos

| Acción | Comando |
| --- | --- |
| Instalar python3-venv (Debian/Ubuntu) | `sudo apt install python3-venv` |
| Instalar o actualizar la app | `./packaging/install.sh` |
| Arrancar TNT (instalado) | `tnt-launcher` |
| Arrancar desde el código | `./run.sh` |
| Modo demostración | `./run.sh --demo` |
| Cambiar el puerto | `TNT_PORT=9000 tnt-launcher` |
| Histórico de un año de HomeBank | `.venv/bin/python scripts/homebank_historico.py preparar` |
| Empaquetar para otro PC | `./packaging/package.sh` |
| Desinstalar conservando la base | `~/.local/share/tnt/packaging/uninstall.sh` |
| Desinstalar borrando la base | `~/.local/share/tnt/packaging/uninstall.sh --purge` |
| Tests automáticos | `./run_tests.sh` |
| Regenerar este manual | `.venv/bin/python scripts/generar_manual.py` |

Hecho por Angus.

«It's a long way to the top if you wanna rock 'n' roll.»
