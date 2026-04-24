"""
TNT — Tus Números Tranquilos
App local de finanzas personales.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, STATIC_DIR
from app.db import init_db
from app.routers import accounts, backup, budgets, categories, dashboard, external_rules, import_page, reconciliations, rules, transactions

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


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


@app.get("/health")
def health():
    return {"status": "ok"}
