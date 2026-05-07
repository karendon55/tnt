#!/usr/bin/env bash
# TNT — Empaquetador para distribución.
#
# Genera dos artefactos en packaging/dist/:
#   tnt-<version>.tar.gz      tarball con el código + scripts de instalación
#   tnt-<version>.sha256      hash para verificar integridad
#
# Uso:
#   ./package.sh                (auto-versión: vYYYYMMDD-shortsha)
#   ./package.sh 1.0.0          (versión explícita)
set -euo pipefail

cd "$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

# Versión: argumento, o variable VERSION, o auto a partir de fecha+commit
if [[ $# -ge 1 ]]; then
    VERSION="$1"
elif [[ -n "${VERSION:-}" ]]; then
    : # ya viene del entorno
elif command -v git >/dev/null 2>&1 && [[ -d .git ]]; then
    VERSION="$(date +%Y%m%d)-$(git rev-parse --short HEAD)"
else
    VERSION="$(date +%Y%m%d)"
fi

PKG_NAME="tnt-${VERSION}"
DIST_DIR="packaging/dist"
STAGE_DIR="$(mktemp -d)/${PKG_NAME}"

mkdir -p "$DIST_DIR" "$STAGE_DIR"

echo "  · Empaquetando $PKG_NAME"

# Listado de exclusiones para tar
EXCLUDES=(
    "--exclude=.git"
    "--exclude=.venv"
    "--exclude=__pycache__"
    "--exclude=*.pyc"
    "--exclude=data/*.db"
    "--exclude=data/*.db-*"
    "--exclude=logs"
    "--exclude=.pytest_cache"
    "--exclude=packaging/dist"
    "--exclude=*.xls"
    "--exclude=*.csv"
    "--exclude=Carga_Homebank_*"
    "--exclude=movements-*.xls"
)

# Creamos el árbol del paquete vía tar (reutiliza las exclusiones)
tar "${EXCLUDES[@]}" -cf - . | (cd "$STAGE_DIR" && tar -xf -)

# README de instalación específico para distribución
cat > "$STAGE_DIR/INSTALAR.txt" <<EOF
TNT — Tus Números Tranquilos
=============================
Versión: $VERSION

Para instalar:

   ./packaging/install.sh

Para desinstalar (preservando la BD):

   ~/.local/share/tnt/packaging/uninstall.sh

Requisitos: Python 3.10+ y conexión para que pip baje las dependencias
(fastapi, uvicorn, jinja2, openpyxl, cryptography, python-multipart).

Tras la instalación, abre TNT desde el menú de aplicaciones (icono del rayo)
o ejecuta: tnt-launcher
EOF

# Tarball final
TARBALL="${DIST_DIR}/${PKG_NAME}.tar.gz"
tar -czf "$TARBALL" -C "$(dirname "$STAGE_DIR")" "$PKG_NAME"

# Hash
sha256sum "$TARBALL" > "${DIST_DIR}/${PKG_NAME}.sha256"

# Limpieza del stage
rm -rf "$(dirname "$STAGE_DIR")"

SIZE_KB="$(du -k "$TARBALL" | cut -f1)"
echo
echo "✓ Paquete creado: $TARBALL  (${SIZE_KB} KB)"
echo "  SHA-256:   $(awk '{print $1}' "${DIST_DIR}/${PKG_NAME}.sha256")"
echo
echo "  Para instalar en otro PC:"
echo "    1) Copia $TARBALL al PC destino"
echo "    2) tar -xzf ${PKG_NAME}.tar.gz"
echo "    3) cd ${PKG_NAME} && ./packaging/install.sh"
