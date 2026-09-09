#!/usr/bin/env bash
# TNT — arranque en local
# Uso: ./run.sh            (base de datos de siempre)
#      ./run.sh --demo     (base de datos de mentira, para probar sin riesgo)
set -euo pipefail

cd "$(dirname "$0")"
APP_DIR="$(pwd)"

# --demo manda sobre .env.local: se fija aquí, y el fichero de ajustes
# respeta un TNT_DB que ya venga puesto.
if [[ "${1:-}" == "--demo" ]]; then
    export TNT_DB="$APP_DIR/data/tnt-demo.db"
    export TNT_DEMO=1
    if [[ ! -f "$TNT_DB" ]]; then
        echo "  No hay base de demostración todavía. Créala con:" >&2
        echo "      TNT_DB=\$PWD/data/tnt-demo.db .venv/bin/python scripts/make_demo_db.py" >&2
        exit 1
    fi
    echo "  (modo demostración: datos inventados)"
    shift
fi

# Ajustes locales de esta máquina (p. ej. TNT_DB). No se sube a git.
if [[ -f "$APP_DIR/.env.local" ]]; then
    set -a; . "$APP_DIR/.env.local"; set +a
fi

export PYTHONPATH="${PYTHONPATH:-}:$APP_DIR"

# La elección de intérprete vive en scripts/pick-python.sh, compartida con
# ./run_tests.sh para que las dos puertas de entrada usen el mismo criterio.
. "$APP_DIR/scripts/pick-python.sh"

PY="$(pick_python || true)"
if [[ -z "$PY" ]]; then
    cat >&2 <<'MSG'
ERROR: no hay ningún Python con uvicorn+fastapi disponible.

Crea el entorno del proyecto:

    python3 -m venv --clear .venv
    .venv/bin/pip install -r requirements.txt

MSG
    exit 1
fi

# El puerto se puede cambiar (PORT=8001 ./run.sh --demo) para levantar la base
# de pruebas sin echar abajo la app instalada, que vive en el 8000.
PORT="${PORT:-8000}"

echo ""
echo "  ⚡ TNT — Tus Números Tranquilos"
echo "  Abriendo http://127.0.0.1:$PORT"
echo ""

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
