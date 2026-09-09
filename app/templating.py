"""
Instancia compartida de Jinja2Templates. Todos los routers la usan
para heredar los globals (app_name, app_tagline) en base.html.
"""
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, APP_TAGLINE, DEMO_MODE, STATIC_DIR, TEMPLATES_DIR
from app.navigation import ACTIVOS_CONFIG, SECCIONES_CONFIG
from app.services.aliases import apply_alias
from app.utils.formatters import eur, eur_signed, num_es, pct_signed

def _version_estaticos() -> str:
    """Sello para romper la caché del navegador cuando cambian CSS o JS.

    Sin esto, tras actualizar TNT el navegador puede seguir sirviendo la hoja
    de estilos anterior durante horas: ves la app a medio pintar y no hay
    forma obvia de saber por qué."""
    ultimo = 0.0
    for f in (STATIC_DIR / "css" / "tnt.css", STATIC_DIR / "js" / "tnt.js"):
        try:
            ultimo = max(ultimo, f.stat().st_mtime)
        except OSError:
            pass
    return str(int(ultimo))


templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["app_name"] = APP_NAME
templates.env.globals["static_version"] = _version_estaticos()
templates.env.globals["app_tagline"] = APP_TAGLINE
templates.env.globals["demo_mode"] = DEMO_MODE
# La subnavegación de Configuración: así _settings_nav.html funciona en
# cualquier sección sin que su handler tenga que pasarla.
templates.env.globals["secciones_config"] = SECCIONES_CONFIG
templates.env.globals["activos_config"] = ACTIVOS_CONFIG

# Filtros de formato es-ES (miles con '.', decimales con ',').
templates.env.filters["eur"] = eur
templates.env.filters["eur_signed"] = eur_signed
templates.env.filters["pct_signed"] = pct_signed
templates.env.filters["num_es"] = num_es
# Alias cosméticos de descripción (BARCO COMPRA EN DEMARY → Demary Fruterías)
templates.env.filters["alias"] = apply_alias
