#!/usr/bin/env bash
# Tests mínimos: importers (ING, CaixaBank, common), formatters, analytics.
# No requiere pytest — se usa unittest de stdlib.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

python3 -m unittest discover -s tests -v "$@"
