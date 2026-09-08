#!/usr/bin/env bash
# TNT — arranque en local
# Uso: ./run.sh
set -euo pipefail

cd "$(dirname "$0")"
APP_DIR="$(pwd)"

# Ajustes locales de esta máquina (p. ej. TNT_DB). No se sube a git.
if [[ -f "$APP_DIR/.env.local" ]]; then
    set -a; . "$APP_DIR/.env.local"; set +a
fi

export PYTHONPATH="${PYTHONPATH:-}:$APP_DIR"

# Decidir intérprete: preferimos uno que tenga uvicorn instalado.
# Mismo criterio que packaging/tnt-launcher.sh, a propósito: no basta con que
# el fichero exista, porque un venv a medio instalar tiene python pero no
# uvicorn. Orden: $TNT_PYTHON > .venv del proyecto > python3 del sistema.
pick_python() {
    local candidate
    for candidate in "${TNT_PYTHON:-}" "$APP_DIR/.venv/bin/python" "$(command -v python3 || true)"; do
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            if "$candidate" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

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

echo ""
echo "  ⚡ TNT — Tus Números Tranquilos"
echo "  Abriendo http://127.0.0.1:8000"
echo ""

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
