"""
TNT — Tus Números Tranquilos
App local de finanzas personales.
"""
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, STATIC_DIR
from app.db import init_db
from app.routers import accounts, aliases, backup, budgets, categories, dashboard, external_rules, import_page, reconciliations, rules, transactions, transfers


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, lifespan=_lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Hosts locales válidos. TNT solo escucha en loopback, pero validar el
# header Host corta el DNS rebinding (una web cuyo dominio resuelve a
# 127.0.0.1 llegaría aquí con Host: evil.com).
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _hostname(value: str) -> str:
    """Extrae el hostname de un header Host ('127.0.0.1:8000') o de un
    Origin ('http://127.0.0.1:8000')."""
    if "//" in value:
        return urlsplit(value).hostname or ""
    return urlsplit(f"//{value}").hostname or ""


@app.middleware("http")
async def _local_only_guard(request: Request, call_next):
    """Defensa CSRF/rebinding para una app de loopback:

    · El Host debe ser local — bloquea DNS rebinding.
    · En métodos con efectos (POST/...), si el navegador manda Origin,
      debe ser también local — bloquea form-POSTs lanzados desde webs
      de terceros contra 127.0.0.1 (borrar movimientos, restaurar BD...).
      Sin Origin (curl, scripts locales) se permite: no es un navegador.
    """
    host = _hostname(request.headers.get("host", ""))
    if host not in _LOCAL_HOSTNAMES:
        return PlainTextResponse("Host no permitido.", status_code=400)

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        if origin and origin.lower() != "null":
            if _hostname(origin) not in _LOCAL_HOSTNAMES:
                return PlainTextResponse("Origen no permitido.", status_code=403)
        elif origin.lower() == "null":
            # 'Origin: null' = contexto opaco (sandbox, file://) — no fiable.
            return PlainTextResponse("Origen no permitido.", status_code=403)

    return await call_next(request)


app.include_router(dashboard.router)
app.include_router(import_page.router)
app.include_router(transactions.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(backup.router)
app.include_router(external_rules.router)
app.include_router(rules.router)
app.include_router(reconciliations.router)
app.include_router(transfers.router)
app.include_router(aliases.router)


@app.get("/health")
def health():
    return {"status": "ok"}
