#!/usr/bin/env bash
# Tests mínimos: importers (ING, CaixaBank, common), formatters, analytics.
# No requiere pytest — se usa unittest de stdlib.
set -euo pipefail

cd "$(dirname "$0")"
APP_DIR="$(pwd)"
export PYTHONPATH="${PYTHONPATH:-}:$APP_DIR"

# Mismo criterio que ./run.sh: el python del sistema puede no tener las
# dependencias tras una actualización, y algunos tests renderizan plantillas.
. "$APP_DIR/scripts/pick-python.sh"
PY="$(pick_python || true)"
if [[ -z "$PY" ]]; then
    echo "ERROR: no hay ningún Python con uvicorn+fastapi. Crea el entorno:" >&2
    echo "    python3 -m venv --clear .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

"$PY" -m unittest discover -s tests -v "$@"
