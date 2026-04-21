"""
Instancia compartida de Jinja2Templates. Todos los routers la usan
para heredar los globals (app_name, app_tagline) en base.html.
"""
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, APP_TAGLINE, TEMPLATES_DIR

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["app_name"] = APP_NAME
templates.env.globals["app_tagline"] = APP_TAGLINE
