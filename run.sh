#!/usr/bin/env bash
# TNT — arranque en local
# Uso: ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

echo ""
echo "  ⚡ TNT — Tus Números Tranquilos"
echo "  Abriendo http://127.0.0.1:8000"
echo ""

exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
