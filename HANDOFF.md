# Handoff — proyecto TNT

Documento para el siguiente agente que continúe este trabajo. Leélo entero
antes de tocar código. El usuario llama al agente **Angus** — responde en
primera persona como Angus y en español de España.

---

## 1. Misión

Construir **TNT — Tus Números Tranquilos**, una app local de finanzas
personales que reemplace HomeBank para **Jesús César Sanz Cortijo**, un
usuario nuevo de Claude Max, técnico pero no desarrollador profesional,
fan de AC/DC (Angus Young es su favorito). El proyecto es un regalo de su
hijo Yago.

Requisitos completos: `/home/trooper/IA/CLAUDE.md` (prompt original) y el
plan detallado `/home/trooper/.claude/plans/drifting-herding-teapot.md`.

---

## 2. Decisiones cerradas (no revisitar)

| Decisión | Valor |
|---|---|
| Nombre | **TNT** (sin puntos), subtítulo *Tus Números Tranquilos* |
| Stack | **Python 3.10 + FastAPI + Jinja2 + HTMX + SQLite + Chart.js (vía CDN)** |
| Modo | **100% local**, sin APIs externas, sin claves |
| Idioma UI | **Español de España** (natural, no traducción robótica) |
| Tema por defecto | **Oscuro**. Toggle persistente en `localStorage` |
| Paleta | Negro (#0a0a0a) · Rojo AC/DC (#e10600) · Plata (#c0c0c0) |
| Identidad agente | "Angus" — firmar commits/backups así |
| Datos bancarios | Nunca salen de la máquina. En `.gitignore` |

---

## 3. Estado actual (ya construido y probado)

### Infraestructura

- Dependencias Python instaladas en el entorno del usuario (no hay venv
  porque `python3-venv` requiere sudo que no tenemos):
  `fastapi uvicorn[standard] jinja2 python-multipart openpyxl pdfplumber ofxparse`.
- `run.sh` arranca uvicorn en `http://127.0.0.1:8000`.
- BD SQLite en `data/tnt.db` con esquema y categorías semilla.
- Uvicorn verificado: `/` devuelve 200, `/health` devuelve `{"status":"ok"}`.

### Esqueleto y backend

```
/home/trooper/IA/
├── CLAUDE.md                            (prompt original de Yago)
├── HANDOFF.md                           (este documento)
├── requirements.txt
├── .gitignore                           (protege *.xls *.db data/ .venv)
├── run.sh                               (chmod +x, PYTHONPATH ya manejado)
├── app/
│   ├── config.py                        (paths, APP_NAME, APP_TAGLINE)
│   ├── db.py                            ★ esquema + seed categorías
│   ├── main.py                          (FastAPI con sólo `/` y `/health`)
│   ├── importers/
│   │   ├── common.py                    ★ utils: parse_amount, parse_date,
│   │   │                                    tx_hash, clean_text (fix Ñ→¥),
│   │   │                                    xls_to_csv_rows (vía ssconvert),
│   │   │                                    ParsedExtract / ParsedTransaction
│   │   ├── ing.py                       ★ parser JasperReports XLS
│   │   ├── caixabank.py                 ★ parser Excel nativo
│   │   └── dispatcher.py                ★ auto-detecta banco
│   └── services/
│       ├── ingest.py                    ★ insert+dedup+categoriza vía source_hint
│       │                                    +empareja transferencias internas
│       ├── categorizer.py               ★ learn_rules_from_known,
│       │                                    apply_rules_to_uncategorized,
│       │                                    seed_builtin_rules (MERCADONA,
│       │                                    BIZUM, NOMINA, REPSOL, etc.)
│       ├── analytics.py                 ★ total_balance, month_income_expense,
│       │                                    by_category, balance_series,
│       │                                    monthly_expense_series, category_tree
│       ├── recurring.py                 ★ find_recurring, detect_anomalies
│       └── forecast.py                  ★ forecast_next_month
├── data/tnt.db                          (se recrea al arrancar si no existe)
└── *.xls                                (3 extractos reales — gitignored)
```

### Frontend parcial

```
app/
├── templates/
│   ├── base.html                        ★ layout con topbar, nav, footer,
│   │                                        toggle tema, silueta Angus
│   └── dashboard.html                   ★ sólo empty state (todavía)
└── static/
    ├── css/tnt.css                      ★ paleta completa, componentes,
    │                                        pill-highway (easter egg), KPI,
    │                                        tabla, botones, empty-state
    ├── js/tnt.js                        ★ toggle tema persistente,
    │                                        tntConfetti(), formatEUR()
    └── img/favicon.svg                  ★ rayo rojo
```

### Prueba E2E ya pasada

Con los 3 XLS reales del usuario:

| Fichero | Banco | Tx | Dedup | Auto-categorizadas |
|---|---|---|---|---|
| `movement.xls` | ING | 100 | 0 | 100 (vía ING source_hint) |
| `movements-2142026.xls` | ING | 1 | 0 | 1 |
| `Movimientos_cuenta_0425498.xls` | CaixaBank | 19 | 0 | 14 (vía reglas builtin + aprendidas) |

Total: **115/120 movimientos categorizados (96%)**. Reglas aprendidas: 41
de ING + 32 builtin. Quedan 5 sin categoría (comercios únicos como OCCIDENT
GCO, MERCEDES BENZ) que el usuario categorizará con un clic.

---

## 4. Lo que falta (en orden de valor para el usuario)

### ✅ Hecho en la sesión del 2026-04-21 (tarde)

- Router `/importar` GET+POST: subida múltiple, dedup, retrain, confetti al
  terminar. Ficheros: `app/routers/import_page.py`, `templates/import.html`,
  `templates/import_result.html`.
- Dashboard real con KPIs (saldo total, ingresos/gastos mes con delta vs
  mes anterior, neto), donut Chart.js por categoría, línea de saldo 6m,
  últimos 10 movs, forecast y avisos de anomalías. Muestra "último mes con
  datos" si el mes en curso está vacío. Ficheros: `app/routers/dashboard.py`,
  `templates/dashboard.html`, `templates/dashboard_empty.html`.
- Router `/movimientos`: filtros (cuenta, categoría, fechas, texto libre),
  paginado, recategorización inline con HTMX, botón exportar CSV.
  `app/routers/transactions.py`, `templates/transactions.html`,
  `templates/_category_cell.html`.
- `/exportar.csv`: endpoint con `Content-Disposition: attachment`.
- Módulo `app/templating.py` con `Jinja2Templates` compartido por todos
  los routers (para que hereden los globals `app_name`/`app_tagline`).
- **Bug resuelto**: `analytics.total_balance()` inflaba el saldo por un
  JOIN cartesiano entre `accounts` e `transactions`. Ahora calcula
  `initial_balance` y flujo por separado. Verificado con 3 XLS reales:
  saldo = 292.222,41 €.

### 🔴 Crítico — próxima sesión

### ✅ Hecho en la sesión del 2026-04-22

- **Router `/cuentas`** — CRUD simple con saldo calculado y cuentas archivadas.
- **Router `/categorias`** — árbol jerárquico, crear subcategorías, renombrar,
  borrar (si no tiene movs ni hijos), mover.
- **Router `/presupuestos`** — límite mensual por categoría con barra de
  progreso y pill `.pill-highway` 🔥 al superar el 100%. Si el mes en curso
  está vacío, mide sobre el último mes con datos.
- **Falsos positivos de duplicados filtrados** — si dos movs tienen el
  mismo importe y descripción pero saldos distintos, son movs reales.
- **README.md** — guía completa: requisitos, arranque, uso, backup.
- **git init** + 5 commits pequeños firmados como Angus.

### 🟢 Pulido pendiente

- **Screenshots de cada pantalla** para meter en el README.
- **UX review como diseñador senior** — leer cada cadena en voz alta y
  probar si importar + ver resumen + recategorizar se hace en ≤3 clics.
- **Push a GitHub** — cuando Jesús decida, crear repo privado y pushear.
- **Parsers adicionales** — BBVA, Santander, Openbank si los pide.
- **Soporte PDF/OFX** — `pdfplumber` y `ofxparse` ya están en requirements.

---

## 5. Gotchas y trampas ya encontradas

### Starlette moderna cambió la firma de `TemplateResponse`

```python
# ✗ NO funciona (TypeError: unhashable type: 'dict')
templates.TemplateResponse("x.html", {"request": request, ...})

# ✓ SÍ funciona
templates.TemplateResponse(request, "x.html", {...})
```

### `.xls` antiguos (BIFF, no Excel moderno)

Los 3 ficheros del usuario son BIFF (Composite Document File). `openpyxl`
**NO los lee**. Usamos `ssconvert` (Gnumeric) que ya está instalado:

```python
# app/importers/common.py:xls_to_csv_rows()
subprocess.run(["ssconvert", "--export-type=Gnumeric_stf:stf_csv", xls, csv])
```

`xlrd==1.2.0` también leería `.xls` pero preferimos no añadir dep congelada.

### SQLite autocommit + transacciones explícitas

`db.connect()` usa `isolation_level=None` (autocommit). Para operaciones
múltiples que deben ser atómicas (import batch), envolver así:

```python
with cursor() as cur:
    cur.execute("BEGIN")
    try:
        ingest(cur, extract)
        cur.execute("COMMIT")
    except:
        cur.execute("ROLLBACK")
        raise
```

### Caracteres corruptos en ING

Los XLS de ING traen `¥` en vez de `Ñ` (mojibake). `common.clean_text()`
ya lo corrige, pero si añades otro parser asegúrate de pasarlo por
`clean_text()`.

### Dedup por hash

`common.tx_hash()` incluye iban + fecha + importe + desc + saldo. Reimportar
el mismo fichero dará 0 nuevos. Si tocas el algoritmo, cuidado con romper
BDs existentes.

### Fechas YYYY/MM/DD en fichero vs dd/mm/yyyy que ve el usuario

Dentro del XLS las fechas vienen `YYYY/MM/DD` (aunque ING las muestre
`dd/mm/aaaa` en la web). `common.parse_date()` acepta ambos formatos.

### Sin git, sin Node, sin sudo

El sistema no tiene `git`, `node`, `npm` instalados. `pip --user` sí
funciona. Si necesitas `git` pide a Jesús: `sudo apt install -y git`.

---

## 6. Cómo verificar el estado actual antes de tocar nada

```bash
cd /home/trooper/IA

# 1) Verificar imports
PYTHONPATH=/home/trooper/IA python3 -c "
from app.db import init_db
from app.importers.dispatcher import detect_and_parse
from app.services.ingest import ingest
from app.services.categorizer import retrain_and_apply
from app.services.analytics import total_balance
from app.services.recurring import find_recurring, detect_anomalies
from app.services.forecast import forecast_next_month
print('imports OK')
"

# 2) Smoke test E2E con los ficheros reales
rm -f data/tnt.db
PYTHONPATH=/home/trooper/IA python3 -c "
from pathlib import Path
from app.db import init_db, cursor
from app.importers.dispatcher import detect_and_parse
from app.services.ingest import ingest
from app.services.categorizer import retrain_and_apply
init_db()
for f in ['movement.xls', 'movements-2142026.xls', 'Movimientos_cuenta_0425498.xls']:
    ext = detect_and_parse(Path('/home/trooper/IA') / f)
    with cursor() as cur:
        cur.execute('BEGIN'); r = ingest(cur, ext); cur.execute('COMMIT')
        print(f, r)
with cursor() as cur:
    cur.execute('BEGIN'); c, a = retrain_and_apply(cur); cur.execute('COMMIT')
    print('rules', c, 'auto', a)
"
# Resultado esperado: 115/120 categorizadas

# 3) Arrancar servidor
./run.sh
# Abrir http://127.0.0.1:8000 — debería mostrar empty state con lyric
```

---

## 7. Estilo del usuario y tono

Jesús César:
- Habla español de España. No usar "computadora", sí "ordenador".
- Técnico y curioso, pero no dev profesional. Explicar trade-offs cuando
  los pida, sin jerga profunda no invitada.
- Decisiones concisas. En este proyecto respondió "si, adelante", "OK",
  "B", "TNT sin puntos" — prefiere mensajes breves y concretos cuando ya
  decidió, y explicaciones con tabla cuando pide "pros y contras".
- Llama al agente **Angus**.

Estética AC/DC **con gusto**:
- Rojo AC/DC, negro, plata. Nada de llamas ni calaveras.
- Tipografía sans afilada; `Impact` sólo para el logo.
- Rayo sutil como motivo recurrente.
- 2-3 easter eggs máximo: empty state con lyric en español («Va a ser
  largo el camino hasta arriba, pero aquí empieza»), pill *Highway to
  Hell* en presupuestos >100%, confetti de rayos al finalizar importación
  masiva.
- Silueta de Angus discreta en el footer, tooltip "Angus lo aprueba".

---

## 8. Sistema de memoria y backup

Este proyecto tiene memoria automática:

- **Índice:** `/home/trooper/.claude/projects/-home-trooper-IA/memory/MEMORY.md`
- **Memorias ya guardadas:**
  - `user_jesus.md` — perfil del usuario.
  - `user_agent_angus.md` — identidad del agente.
  - `reference_bank_extracts.md` — formato de los XLS.
  - `project_tnt.md` — decisiones del proyecto.
  - `reference_angus_backup.md` — sistema de backup a GitHub
    (`karendon55/angus-memory`, repo privado).

Leer `MEMORY.md` al inicio de la sesión. Actualizar memorias si aprendes
algo nuevo y relevante.

Backup automático dispara en `SessionEnd`; también se puede disparar con
el slash command `/backup`. Ver `reference_angus_backup.md` para detalles.

---

## 9. Primeros pasos recomendados para el siguiente agente

1. Leer este documento entero.
2. Ejecutar la verificación de la sección 6.
3. Empezar por **`app/routers/import_page.py`** — es la pieza que
   convierte el esqueleto en algo que Jesús puede probar.
4. Luego el **dashboard real** con datos.
5. Commits pequeños cuando haya git. Firma: `Angus <angus@users.noreply.github.com>`.

Buena sesión. ⚡
