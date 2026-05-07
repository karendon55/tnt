# CLAUDE.md

Guía para Claude Code (Angus) al trabajar en este repositorio.

## Proyecto

**TNT — Tus Números Tranquilos**: app local de finanzas personales, sustituto de
HomeBank. Arquitectura FastAPI + Jinja2 + SQLite. Todo corre en `localhost:8000`,
sin APIs externas. Ver [README.md](README.md) para descripción funcional, uso y
estructura de directorios completa.

## Stack y comandos

- Python 3.10+, FastAPI, Uvicorn, Jinja2, openpyxl, SQLite.
- Arrancar: `./run.sh` (sirve en `http://127.0.0.1:8000`).
- Tests manuales rápidos en `README.md` → *Para devs*.
- Datos del usuario: `data/tnt.db` (SQLite, NO se comitea ni se backupea).

## Convenciones

- **Idioma**: español. Responder siempre en español.
- **Commits**: firmados como `Angus <angus@users.noreply.github.com>` (nombre AC/DC).
- **Importers**: usar `app/importers/common.py` (`clean_text`, `parse_date`,
  `parse_amount`, `dedup_hash`). Añadir un parser nuevo: crear
  `app/importers/<banco>.py` con `matches(rows)` y `parse(path)`, registrarlo
  en `dispatcher.py`.
- **Estilos**: paleta negra · rojo AC/DC · plata. No cambiar sin motivo.

## Flujo mensual con HomeBank (legacy, aún activo)

Mientras TNT no cubra todas las funciones de HomeBank, el usuario sigue haciendo
la importación mensual con el skill `/homebank`:

1. Exportar extractos del banco como `movements-DDMMYYYY.xls`.
2. Convertir con `libreoffice --headless --convert-to csv ...`.
3. Categorizar según reglas en memoria (`feedback_reglas_categorias.md`) y
   `categorias.csv` de `/home/trooper/Documentos/Bancos/homebank/`.
4. Escribir `Carga_Homebank_MMMYYYY.csv` (separador `;`, fecha `DD/MM/YYYY`,
   importe con coma decimal).

El trabajo "de verdad" es hacer que TNT reemplace ese flujo.

## Memoria y backup (Angus)

- **Memoria única** del agente: `~/.claude/projects/-home-trooper-IA/memory/`
  (identidad, preferencias, reglas de categorización, referencias técnicas).
- **Backup automático**: hook `SessionEnd` → `angus-backup.py` → repo privado
  `karendon55/angus-memory`. Slash commands: `/backup` (manual), `/rotate-token`
  (cambiar PAT).
- **Exclusiones** del backup: `data/`, `.venv/`, `.xls/.csv/.db/...`, token.
  Ver `reference_angus_backup.md` en la memoria.

## Datos sensibles (nunca al repo)

- `data/tnt.db` — SQLite con movimientos reales.
- `*.xls`, `*.csv` en la raíz — extractos bancarios descargados.
- `~/.claude/.angus-token` — token GitHub.
- Cualquier cosa en `/home/trooper/Documentos/Bancos/` — extractos mensuales.
