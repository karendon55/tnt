#!/usr/bin/env bash
# TNT — Lanzador para escritorio.
#
# Arranca uvicorn en segundo plano sobre 127.0.0.1:PUERTO, espera a que el
# servidor responda y abre el navegador del usuario en la URL principal.
# Si el servidor ya está corriendo (otra ventana abierta) solo abre el navegador.
#
# Variables que se pueden sobrescribir desde el entorno:
#   TNT_PORT     puerto a usar (por defecto 8000)
#   TNT_HOST     interfaz (por defecto 127.0.0.1)
#   TNT_HOME     ruta a la app TNT instalada (por defecto, autodetectada)
#   TNT_PYTHON   intérprete Python a usar (por defecto, .venv si existe; si no python3)
#
# Códigos de salida:
#   0  todo bien
#   1  no se encontró Python
#   2  no se pudo arrancar el servidor en 20s
set -u

PORT="${TNT_PORT:-8000}"
HOST="${TNT_HOST:-127.0.0.1}"

# Localizar la raíz de TNT — orden:
#   1) $TNT_HOME si está definida
#   2) Directorio donde vive este script si contiene app/main.py (modo "ejecutar desde fuente")
#   3) Resolver simlinks (instalado en ~/.local/bin/tnt) y subir a la raíz
SELF="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SELF")"
if [[ -n "${TNT_HOME:-}" && -f "$TNT_HOME/app/main.py" ]]; then
    APP_DIR="$TNT_HOME"
elif [[ -f "$SCRIPT_DIR/app/main.py" ]]; then
    APP_DIR="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/../app/main.py" ]]; then
    APP_DIR="$(readlink -f "$SCRIPT_DIR/..")"
elif [[ -f "$HOME/.local/share/tnt/app/main.py" ]]; then
    APP_DIR="$HOME/.local/share/tnt"
else
    notify-send "TNT" "No se encuentra la instalación de TNT (app/main.py)." 2>/dev/null
    echo "ERROR: no se encuentra app/main.py" >&2
    exit 1
fi

cd "$APP_DIR"
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# Decidir intérprete: preferimos uno que tenga uvicorn instalado.
# Orden: $TNT_PYTHON > .venv > python3 del sistema.
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
    notify-send "TNT" "No hay un Python 3 con uvicorn+fastapi disponibles." 2>/dev/null
    echo "ERROR: no hay un Python con uvicorn+fastapi" >&2
    exit 1
fi

# Si ya hay un servidor escuchando en el puerto, asumimos que es nuestro y reutilizamos.
already_up() {
    # /health responde {"status":"ok"} si es TNT
    local code
    code=$(curl -fsS -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}/health" 2>/dev/null || echo "000")
    [[ "$code" == "200" ]]
}

start_server() {
    local logf="$APP_DIR/logs/tnt-$(date +%Y%m%d).log"
    # nohup + setsid para que TNT siga vivo aunque cerremos el terminal de origen
    PYTHONPATH="$APP_DIR" nohup setsid "$PY" -m uvicorn app.main:app \
        --host "$HOST" --port "$PORT" --log-level info \
        >> "$logf" 2>&1 &
    echo $!
}

wait_for_ready() {
    for i in $(seq 1 40); do
        if already_up; then return 0; fi
        sleep 0.5
    done
    return 1
}

open_browser() {
    local url="http://${HOST}:${PORT}/"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser "$url" >/dev/null 2>&1 &
    elif command -v firefox >/dev/null 2>&1; then
        firefox "$url" >/dev/null 2>&1 &
    else
        echo "Abre tu navegador en: $url"
    fi
}

if already_up; then
    open_browser
    exit 0
fi

start_server >/dev/null

if wait_for_ready; then
    open_browser
    exit 0
else
    notify-send "TNT" "El servidor no respondió en 20 s. Revisa $APP_DIR/logs/" 2>/dev/null
    echo "ERROR: timeout esperando al servidor" >&2
    exit 2
fi
