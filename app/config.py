from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "tnt.db"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
DEFAULT_EXTRACTS_DIR = BASE_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_NAME = "TNT"
APP_TAGLINE = "Tus Números Tranquilos"
