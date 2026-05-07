#!/usr/bin/env bash
# TNT — Desinstalador.
#
# Por defecto NO borra la carpeta data/ (tu BD). Para borrarla también:
#   ./uninstall.sh --purge
#
set -euo pipefail

PREFIX="$HOME/.local"
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --prefix=*) PREFIX="${arg#--prefix=}" ;;
        --purge)    PURGE=1 ;;
        -h|--help)
            cat <<HELP
Desinstalador de TNT.
  --prefix=PATH   raíz donde estaba instalado (por defecto \$HOME/.local)
  --purge         borrar también la BD del usuario (data/)
HELP
            exit 0
            ;;
        *) echo "Opción no reconocida: $arg" >&2; exit 2 ;;
    esac
done

APP_DIR="$PREFIX/share/tnt"
BIN_DIR="$PREFIX/bin"
DESKTOP_FILE="$PREFIX/share/applications/tnt.desktop"
ICON_BASE="$PREFIX/share/icons/hicolor"

# Parar instancias en curso
if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    echo "  · Parando instancias de TNT en curso"
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 1
fi

# Quitar lanzador y atajo
rm -f "$BIN_DIR/tnt-launcher" "$BIN_DIR/tnt"

# Quitar .desktop
rm -f "$DESKTOP_FILE"

# Quitar iconos
for size in 16 32 48 64 128 256; do
    rm -f "$ICON_BASE/${size}x${size}/apps/tnt.png"
done
rm -f "$ICON_BASE/scalable/apps/tnt.svg"

# Quitar el directorio de la app (preservando data/ si no se hace --purge)
if [[ -d "$APP_DIR" ]]; then
    if [[ "$PURGE" -eq 1 ]]; then
        echo "  · Borrando $APP_DIR (incluida BD)"
        rm -rf "$APP_DIR"
    else
        echo "  · Borrando $APP_DIR (preservando data/)"
        # Mover data/ a un sitio temporal, borrar todo, restaurar data/
        if [[ -d "$APP_DIR/data" ]]; then
            BACKUP_DATA="$(mktemp -d)/data"
            mv "$APP_DIR/data" "$BACKUP_DATA"
        fi
        rm -rf "$APP_DIR"
        if [[ -n "${BACKUP_DATA:-}" && -d "$BACKUP_DATA" ]]; then
            mkdir -p "$APP_DIR"
            mv "$BACKUP_DATA" "$APP_DIR/data"
            echo "  · Tu BD sigue en $APP_DIR/data/"
        fi
    fi
fi

# Refrescar caches del escritorio
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "$ICON_BASE" 2>/dev/null || true
fi

echo
echo "✓ TNT desinstalado."
if [[ "$PURGE" -eq 0 && -d "$APP_DIR/data" ]]; then
    echo "  Para borrar también la BD: ./uninstall.sh --purge"
fi
