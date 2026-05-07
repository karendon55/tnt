# TNT — Tus Números Tranquilos

App local de finanzas personales. Sustituto de HomeBank, 100% en tu ordenador,
sin APIs externas, sin claves, sin nube.

Paleta negra · rojo AC/DC · plata. Tema oscuro por defecto. ⚡

## Requisitos

- Linux (probado en Ubuntu 24.04)
- Python 3.10+
- `ssconvert` (Gnumeric) para leer los `.xls` antiguos del banco:
  ```bash
  sudo apt install gnumeric
  ```
- Paquetes Python del `requirements.txt`:
  ```bash
  pip install --user -r requirements.txt
  ```

## Arrancar

```bash
./run.sh
```

Abre <http://127.0.0.1:8000>. La primera vez se crea automáticamente
`data/tnt.db` con las categorías semilla.

## Uso

1. **Importar** → sube tus `.xls` de ING o CaixaBank (puedes seleccionar
   varios a la vez). Se ignoran duplicados automáticamente y se emparejan
   las transferencias entre tus cuentas.
2. **Panel** → saldo total, ingresos/gastos del mes, donut por categoría,
   evolución del saldo, últimos movimientos y previsión del mes siguiente.
3. **Movimientos** → lista filtrable por cuenta, categoría, fechas y texto.
   Puedes recategorizar cualquier movimiento en un clic.
4. **Cuentas** → crear, editar y archivar. El saldo se calcula solo.
5. **Categorías** → árbol jerárquico, crear subcategorías, renombrar.
6. **Presupuestos** → límite mensual por categoría con barra de progreso.
   Cuando se pasa del 100% aparece la pill *Highway to Hell*. 🔥

### Exportar

Desde la pestaña **Movimientos** hay un botón *Exportar CSV* que descarga
todos los movimientos filtrados en formato CSV (separador `;`, apto para
abrir en Excel o LibreOffice en España).

## Backup

Todos tus datos viven en `data/tnt.db` (SQLite). Tienes tres formas:

**1. Backup local plano** (`/backup` POST, también desde el panel)
Copia `data/tnt.db` a las rutas configuradas en `app/routers/backup.py`
(`~/Dropbox`, `~/Documentos/contabilidad/backup`, …). Sobrescribe la copia
anterior, escribe a `.tmp` y hace rename atómico.

**2. Backup cifrado descargable** (`/backup` página → "Backup cifrado")
Genera un fichero `tnt-backup-YYYYMMDD-HHMMSS.tnt` cifrado con la contraseña
que tú elijas. Por debajo: PBKDF2-HMAC-SHA256 con 480 000 iteraciones para
derivar la clave + Fernet (AES-128-CBC + HMAC-SHA256) para cifrar y firmar.
Si pierdes la contraseña, el contenido es irrecuperable.

**3. Restaurar desde un `.tnt`** (misma página)
Sube el fichero, mete la contraseña y reemplaza la BD. Antes de sobrescribir
deja una copia de seguridad de la BD actual con sufijo `.before-restore-XXXXXXXX`
por si quieres deshacer.

```bash
# Manual también funciona:
cp data/tnt.db ~/Copias/tnt-$(date +%Y%m%d).db
```

## Instalar como aplicación de escritorio

Para usar TNT como una app más del menú (icono del rayo AC/DC en el menú
de aplicaciones, sin tener que arrancarlo desde la terminal):

```bash
./packaging/install.sh
```

> **Nota para Debian/Ubuntu:** el módulo `venv` viene en un paquete aparte.
> Si el instalador aborta con *«ensurepip is not available»*, instala primero:
>
> ```bash
> sudo apt install python3-venv
> # o, si esa fórmula no encuentra el paquete:
> sudo apt install python3.10-venv
> ```
>
> El instalador detecta esta situación al inicio y aborta con un mensaje claro
> sin tocar nada en tu sistema.

Esto instala en el HOME del usuario (sin root):

| Ruta                                              | Contenido                |
|---------------------------------------------------|--------------------------|
| `~/.local/share/tnt/`                             | código + venv + data/    |
| `~/.local/bin/tnt-launcher` (y `tnt`)             | wrapper ejecutable       |
| `~/.local/share/applications/tnt.desktop`         | entrada del menú         |
| `~/.local/share/icons/hicolor/*/apps/tnt.{svg,png}` | iconos en varios tamaños |

Después: doble click en *TNT* desde el menú, o ejecuta `tnt-launcher` en cualquier
terminal — arranca uvicorn y abre tu navegador en `http://127.0.0.1:8000`.

Para desinstalar (preservando la BD):

```bash
~/.local/share/tnt/packaging/uninstall.sh
# o con --purge para borrar también data/
```

## Distribuir TNT a otro PC

```bash
./packaging/package.sh                # auto-versión por fecha+commit
./packaging/package.sh 1.0.0          # versión explícita
```

Crea `packaging/dist/tnt-<versión>.tar.gz` (~150 KB, sin BD ni extractos)
y un fichero `.sha256` para verificar. En el PC destino:

```bash
tar -xzf tnt-<versión>.tar.gz
cd tnt-<versión>
./packaging/install.sh
```

## Estructura del proyecto

```
app/
├── config.py            # Rutas y constantes
├── db.py                # SQLite: esquema + semilla de categorías
├── main.py              # FastAPI: monta routers y estáticos
├── templating.py        # Instancia compartida de Jinja2Templates
├── importers/
│   ├── common.py        # Utilidades (parse_date, parse_amount, dedup hash)
│   ├── dispatcher.py    # Detecta el banco y delega al parser
│   ├── ing.py           # Parser ING (formato JasperReports)
│   └── caixabank.py     # Parser CaixaBank (Excel nativo)
├── routers/
│   ├── dashboard.py     # Panel principal
│   ├── import_page.py   # Subir y procesar extractos
│   ├── transactions.py  # Lista de movimientos + export CSV
│   ├── accounts.py      # CRUD de cuentas
│   ├── categories.py    # Árbol de categorías
│   └── budgets.py       # Presupuestos mensuales
├── services/
│   ├── ingest.py        # Insertar + dedup + emparejar transferencias
│   ├── categorizer.py   # Reglas builtin + aprendidas
│   ├── analytics.py     # KPIs y series
│   ├── recurring.py     # Recurrentes + anomalías
│   └── forecast.py      # Previsión del mes siguiente
├── static/
│   ├── css/tnt.css      # Estilos
│   ├── js/tnt.js        # Tema + confeti
│   └── img/favicon.svg  # Rayo rojo
└── templates/           # Jinja2
```

## Diferencias respecto a HomeBank

**Lo que TNT hace y HomeBank no**:
- Auto-categorización con reglas que aprende de tu propio historial.
- Detección de transferencias internas entre tus cuentas.
- Previsión del saldo del mes siguiente basada en recurrentes detectados.
- Avisos automáticos: posibles duplicados y subidas de precio.
- UI moderna con tema oscuro y gráficos en vivo.

**Lo que HomeBank hace y TNT no (todavía)**:
- Múltiples divisas en una misma cuenta.
- Importar/exportar formato HomeBank `.xhb`.
- Reportes imprimibles en PDF.
- Conciliación bancaria marca-a-marca.

Si necesitas algo de eso, pídeselo a Angus y lo añadimos.

## Para devs

### Tests manuales rápidos

```bash
# Verificar imports
PYTHONPATH=. python3 -c "from app.main import app; print('OK')"

# Smoke test con extractos reales en el directorio raíz
rm -f data/tnt.db
PYTHONPATH=. python3 -c "
from pathlib import Path
from app.db import init_db, cursor
from app.importers.dispatcher import detect_and_parse
from app.services.ingest import ingest
from app.services.categorizer import retrain_and_apply
init_db()
for f in Path('.').glob('*.xls'):
    ext = detect_and_parse(f)
    with cursor() as cur:
        cur.execute('BEGIN'); r = ingest(cur, ext); cur.execute('COMMIT')
        print(f.name, r)
with cursor() as cur:
    cur.execute('BEGIN'); c, a = retrain_and_apply(cur); cur.execute('COMMIT')
    print('reglas', c, 'auto', a)
"
```

### Añadir un parser nuevo

1. Crea `app/importers/mi_banco.py` con `matches(rows)` y `parse(path)`.
2. Registra en `app/importers/dispatcher.py`.
3. Usa siempre `common.clean_text()` y `common.parse_date()` para normalizar.

---

Hecho con ⚡ por **Angus**.
*«It's a long way to the top if you wanna rock 'n' roll.»*
