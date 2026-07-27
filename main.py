"""
main.py – MTG App Pro Backend Entrypoint

Initialisiert die FastAPI-App, registriert Middleware (CORS), 
globalen Exception-Handler, Lifespan-Events für die DB-Verbindung 
und inkludiert alle modularen API-Router.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

# Muss laufen, BEVOR irgendein lokales Modul importiert wird: database.py
# (DATABASE_URL), services/limiter.py und services/cache.py lesen ihre
# jeweilige *_URL-Konfiguration bereits beim Import (Modul-/Klassenebene),
# nicht erst bei einem Funktionsaufruf. Vorher lag load_dotenv() nur in
# auth.py, das über routers.auth erst NACH database/limiter/cache importiert
# wird -- .env-Werte kamen dadurch bei diesen drei Modulen nie an, nur
# echte (z.B. von Docker gesetzte) Umgebungsvariablen wurden gesehen.
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from database import init_db
from services.limiter import limiter
from routers import cards, auth, collection, decks, ai, payments, vision

# ======================================================================
# Logging: zentral hier konfiguriert (Entrypoint). Jedes Modul nutzt
# `logging.getLogger(__name__)`; Level ist über LOG_LEVEL steuerbar
# (z.B. "DEBUG" in der Entwicklung, Default "INFO").
# ======================================================================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ======================================================================
# CORS: erlaubte Origins
# ======================================================================
# Nur für lokale Entwicklung -- der Vite-Dev-Server aus mtg-frontend/vite.config.js.
DEV_ORIGINS = ["http://localhost:5175", "http://127.0.0.1:5175"]

def get_allowed_origins() -> list[str]:
    """
    Liest ALLOWED_ORIGINS (kommagetrennte Domainliste) aus der Umgebung.
    Ist die Variable gesetzt, gilt das als Produktions-/Staging-Deploy und
    NUR diese Domains werden erlaubt -- localhost wird dann nicht automatisch
    hinzugefügt. Ist sie leer/unset, wird von lokaler Entwicklung ausgegangen
    und nur der lokale Vite-Dev-Server darf zugreifen.
    """
    configured = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return configured if configured else DEV_ORIGINS

# ======================================================================
# Lifespan Events (Datenbank-Initialisierung beim Startup)
# ======================================================================
MAINTENANCE_INTERVAL_SECONDS = int(os.getenv("MAINTENANCE_INTERVAL_SECONDS", "1800"))
JOB_RETENTION_HOURS = int(os.getenv("JOB_RETENTION_HOURS", "24"))


async def _run_maintenance() -> None:
    """
    Räumt periodisch auf, damit die App im Dauerbetrieb nicht zuwächst:
    - erledigte Hintergrund-Jobs (synergy_jobs, import_jobs) älter als
      JOB_RETENTION_HOURS -- sie wurden bisher nie gelöscht, die Tabellen
      wuchsen also mit jeder Analyse und jedem Import unbegrenzt.
    - abgelaufene Cache-Einträge (nur relevant ohne Redis).
    """
    from datetime import datetime, timedelta
    from sqlalchemy import text as sql_text

    from database import get_db_session
    from services.cache import scryfall_cache

    cutoff = datetime.utcnow() - timedelta(hours=JOB_RETENTION_HOURS)
    try:
        async with get_db_session() as session:
            for tabelle in ("synergy_jobs", "import_jobs"):
                # erstellt_am IS NULL: Alt-Zeilen aus der Zeit, als der
                # Zeitstempel bei Roh-SQL-Inserts nicht gesetzt wurde.
                await session.execute(
                    sql_text(
                        f"DELETE FROM {tabelle} "
                        "WHERE erstellt_am < :cutoff OR erstellt_am IS NULL"
                    ),
                    {"cutoff": cutoff},
                )
    except Exception:
        logger.warning("Job-Aufräumen fehlgeschlagen", exc_info=True)

    try:
        entfernt = await asyncio.to_thread(scryfall_cache.flush_expired)
        if entfernt:
            logger.info("Cache-Wartung: %d abgelaufene Einträge entfernt.", entfernt)
    except Exception:
        logger.warning("Cache-Aufräumen fehlgeschlagen", exc_info=True)


async def _maintenance_loop() -> None:
    while True:
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
        await _run_maintenance()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starte Datenbankverbindung...")
    try:
        await init_db()
        logger.info("Datenbank erfolgreich initialisiert. Backend ist BEREIT!")
    except Exception:
        logger.exception("FEHLER bei der Datenbankinitialisierung")

    wartung = asyncio.create_task(_maintenance_loop())
    try:
        yield
    finally:
        wartung.cancel()
        try:
            await wartung
        except (asyncio.CancelledError, Exception):
            pass

# ======================================================================
# FastAPI App Setup
# ======================================================================
app = FastAPI(
    title="MTG App Pro Backend",
    description="Refaktoriertes modulares FastAPI Backend für Magic: The Gathering Karten- und Decksverwaltung.",
    version="1.0.0",
    lifespan=lifespan
)

# ======================================================================
# Rate Limiting (slowapi, Redis-backed über services/limiter.py)
# ======================================================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ======================================================================
# CORS Middleware
# ======================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================================
# Globaler Exception Handler
# ======================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("GLOBALER FEHLER bei %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"erfolg": False, "error": str(exc)}
    )

# ======================================================================
# Router Inkludierung
# ======================================================================
app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(collection.router)
app.include_router(decks.router)
app.include_router(ai.router)
app.include_router(payments.router)
app.include_router(vision.router)

# ======================================================================
# Server-Status Endpoint
# ======================================================================
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "Grana App API is running and healthy"}