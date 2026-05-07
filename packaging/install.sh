#!/usr/bin/env bash
# TNT — Instalador de usuario para Linux.
#
# Instala TNT en el HOME del usuario (sin necesidad de root):
#   ~/.local/share/tnt/             ← código + venv + carpeta data
#   ~/.local/bin/tnt-launcher       ← comando ejecutable
#   ~/.local/share/applications/tnt.desktop
#   ~/.local/share/icons/hicolor/<tamaño>/apps/tnt.png
#
# Uso:
#   ./install.sh                 (instalación normal)
#   ./install.sh --no-venv       (no crea venv, usa python3 del sistema)
#   ./install.sh --prefix=/foo   (raíz alternativa, p.ej. en pendrive)
#
set -euo pipefail

# ---------- argumentos ----------
PREFIX="$HOME/.local"
USE_VENV=1
for arg in "$@"; do
    case "$arg" in
        --prefix=*)   PREFIX="${arg#--prefix=}" ;;
        --no-venv)    USE_VENV=0 ;;
        -h|--help)
            cat <<HELP
Instalador de TNT.
  --prefix=PATH   raíz de instalación (por defecto \$HOME/.local)
  --no-venv       no crear entorno virtual; usar python3 del sistema
HELP
            exit 0
            ;;
        *) echo "Opción no reconocida: $arg" >&2; exit 2 ;;
    esac
done

# ---------- localizar el origen ----------
SRC_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
if [[ ! -f "$SRC_DIR/app/main.py" ]]; then
    echo "ERROR: no se encuentra app/main.py en $SRC_DIR" >&2
    exit 1
fi

# ---------- comprobar Python ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: necesitas python3 (>=3.10) instalado." >&2
    exit 1
fi
PY_VERSION="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
PY_MAJ="$(python3 -c 'import sys; print(sys.version_info[0])')"
PY_MIN="$(python3 -c 'import sys; print(sys.version_info[1])')"
if [[ "$PY_MAJ" -lt 3 || ( "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 10 ) ]]; then
    echo "ERROR: necesitas Python 3.10 o superior (tienes $PY_VERSION)." >&2
    exit 1
fi
echo "  · Python $PY_VERSION OK"

# Comprobamos que ensurepip está disponible — sin él, `python3 -m venv` falla
# con "ensurepip is not available". En Debian/Ubuntu hay que instalar
# python3-venv (o python3.X-venv) aparte.
if [[ "$USE_VENV" -eq 1 ]] && ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    cat >&2 <<MSG
ERROR: tu Python no tiene 'ensurepip', así que no se puede crear el entorno
       virtual con 'python3 -m venv'.

       En Debian/Ubuntu instala el paquete del módulo venv:

           sudo apt install python3-venv
           # o, si lo anterior no encuentra el paquete:
           sudo apt install python$PY_VERSION-venv

       Luego vuelve a lanzar este instalador.

       Si prefieres no crear venv y usar directamente el python3 del sistema
       (asegúrate de que tiene fastapi, uvicorn, jinja2, openpyxl, cryptography
       y python-multipart instalados con 'pip install --user'), lanza:

           ./packaging/install.sh --no-venv
MSG
    exit 1
fi

# ---------- destinos ----------
APP_DIR="$PREFIX/share/tnt"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_BASE="$PREFIX/share/icons/hicolor"

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"

# ---------- copiar código ----------
echo "  · Copiando código a $APP_DIR"
# Lo copiamos con rsync si está; si no, con tar.
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='data/*.db' --exclude='data/*.db-*' \
        --exclude='*.pyc' --exclude='logs' --exclude='.pytest_cache' \
        --exclude='packaging/dist' \
        "$SRC_DIR"/ "$APP_DIR"/
else
    (cd "$SRC_DIR" && tar --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
        --exclude='data/*.db' --exclude='*.pyc' --exclude='logs' \
        --exclude='packaging/dist' \
        -cf - .) | (cd "$APP_DIR" && tar -xf -)
fi
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# ---------- entorno virtual y dependencias ----------
if [[ "$USE_VENV" -eq 1 ]]; then
    echo "  · Creando entorno virtual en $APP_DIR/.venv"
    python3 -m venv "$APP_DIR/.venv"
    PIP="$APP_DIR/.venv/bin/pip"
    "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip --quiet
    echo "  · Instalando dependencias"
    "$PIP" install --quiet -r "$APP_DIR/requirements.txt"
else
    echo "  · No se crea venv (--no-venv); comprobando dependencias en python3"
    if ! python3 -c "import fastapi, uvicorn, jinja2, openpyxl, cryptography" >/dev/null 2>&1; then
        echo "  ! Faltan dependencias. Ejecuta:"
        echo "      python3 -m pip install --user -r $APP_DIR/requirements.txt"
    fi
fi

# ---------- icono (varios tamaños) ----------
echo "  · Instalando iconos"
for size in 16 32 48 64 128 256; do
    target="$ICON_BASE/${size}x${size}/apps"
    mkdir -p "$target"
    cp "$SRC_DIR/packaging/icons/tnt-${size}.png" "$target/tnt.png"
done
mkdir -p "$ICON_BASE/scalable/apps"
cp "$SRC_DIR/packaging/icons/tnt.svg" "$ICON_BASE/scalable/apps/tnt.svg"

# ---------- lanzador en bin ----------
echo "  · Instalando lanzador en $BIN_DIR/tnt-launcher"
# Generamos un wrapper en bin/ que fija TNT_HOME y ejecuta el lanzador real
# (que vive con el código). Así el launcher sigue siendo único.
cat > "$BIN_DIR/tnt-launcher" <<EOF
#!/usr/bin/env bash
# Wrapper generado por install.sh — fija TNT_HOME y delega al launcher real.
export TNT_HOME="$APP_DIR"
exec "\$TNT_HOME/packaging/tnt-launcher.sh" "\$@"
EOF
chmod 755 "$BIN_DIR/tnt-launcher"

# Atajo corto: 'tnt' es alias del launcher (mismo wrapper).
cat > "$BIN_DIR/tnt" <<EOF
#!/usr/bin/env bash
exec "$BIN_DIR/tnt-launcher" "\$@"
EOF
chmod 755 "$BIN_DIR/tnt"

# ---------- entrada en el menú ----------
echo "  · Instalando entrada de menú"
DESKTOP_FILE="$DESKTOP_DIR/tnt.desktop"
sed "s|^Exec=.*|Exec=$BIN_DIR/tnt-launcher|" \
    "$SRC_DIR/packaging/tnt.desktop" > "$DESKTOP_FILE"
chmod 644 "$DESKTOP_FILE"

# ---------- refrescar caches del escritorio ----------
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "$ICON_BASE" 2>/dev/null || true
fi

# ---------- comprobación final ----------
echo
echo "✓ TNT instalado."
echo
echo "  Datos del usuario: $APP_DIR/data/  (BD persistente; no se sobrescribe al reinstalar)"
echo "  Lanzador:          $BIN_DIR/tnt-launcher"
echo "  Entrada menú:      $DESKTOP_FILE"
echo
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "  ⚠️  $BIN_DIR no está en tu \$PATH. Añade:"
       echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
       echo "      en tu ~/.bashrc o ~/.zshrc, o usa el lanzador desde el menú." ;;
esac
echo
echo "  Para arrancar TNT:"
echo "    · Doble click en el icono 'TNT' del menú de aplicaciones, o"
echo "    · Ejecuta:  tnt-launcher  (abrirá el navegador en http://127.0.0.1:8000)"
echo
echo "  Para desinstalar:  $APP_DIR/packaging/uninstall.sh"
