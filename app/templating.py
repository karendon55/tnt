"""
Instancia compartida de Jinja2Templates. Todos los routers la usan
para heredar los globals (app_name, app_tagline) en base.html.
"""
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, APP_TAGLINE, TEMPLATES_DIR
from app.services.aliases import apply_alias
from app.utils.formatters import eur, eur_signed, num_es, pct_signed

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["app_name"] = APP_NAME
templates.env.globals["app_tagline"] = APP_TAGLINE

# Filtros de formato es-ES (miles con '.', decimales con ',').
templates.env.filters["eur"] = eur
templates.env.filters["eur_signed"] = eur_signed
templates.env.filters["pct_signed"] = pct_signed
templates.env.filters["num_es"] = num_es
# Alias cosméticos de descripción (BARCO COMPRA EN DEMARY → Demary Fruterías)
templates.env.filters["alias"] = apply_alias
