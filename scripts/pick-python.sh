# Elegir intérprete de Python. Lo comparten ./run.sh y ./run_tests.sh.
#
# No basta con que el binario exista: tras una actualización del sistema el
# python3 de turno puede no tener las dependencias, y un venv a medio instalar
# tiene python pero no uvicorn. Por eso el criterio es que el candidato pueda
# importar de verdad lo que hace falta.
#
# packaging/tnt-launcher.sh lleva su propia copia a propósito: viaja solo
# dentro de la app instalada, sin este fichero al lado.
#
# Uso:  . scripts/pick-python.sh ; PY="$(pick_python)"
# Orden: $TNT_PYTHON > .venv del proyecto > python3 del sistema.
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
