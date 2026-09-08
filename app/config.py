import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Dónde vive la base de datos. Por defecto, data/tnt.db junto al código, que es
# lo que usa la app instalada. Con TNT_DB se apunta a otra ruta: así el servidor
# de desarrollo puede trabajar contra la base real en vez de contra una copia
# que se va quedando vieja.
#
# OJO: si TNT_DB apunta a datos reales, cualquier prueba de importación,
# restauración o borrado los toca de verdad. No hay red debajo.
_DB_ENV = os.environ.get("TNT_DB", "").strip()
DB_PATH = Path(_DB_ENV).expanduser() if _DB_ENV else BASE_DIR / "data" / "tnt.db"
DATA_DIR = DB_PATH.parent

# Modo demostración: lo enciende ./run.sh --demo. Explícito a propósito —
# adivinarlo por el nombre del fichero marcaría como "de mentira" cualquier
# base que no fuera la de siempre.
DEMO_MODE = os.environ.get("TNT_DEMO") == "1"

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
DEFAULT_EXTRACTS_DIR = BASE_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "TNT"
APP_TAGLINE = "Tus Números Tranquilos"
