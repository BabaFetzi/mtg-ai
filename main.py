"""
main.py – MTG App Pro Backend Entrypoint

Initialisiert die FastAPI-App, registriert Middleware (CORS), 
globalen Exception-Handler, Lifespan-Events für die DB-Verbindung 
und inkludiert alle modularen API-Router.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from database import init_db
from routers import cards, auth, collection, decks, ai, payments, vision

# ======================================================================
# Lifespan Events (Datenbank-Initialisierung beim Startup)
# ======================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starte Datenbankverbindung...")
    try:
        await init_db()
        print("Datenbank erfolgreich initialisiert. Backend ist BEREIT!")
    except Exception as e:
        print(f"FEHLER bei der Datenbankinitialisierung: {e}")
    yield

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
# CORS Middleware
# ======================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================================
# Globaler Exception Handler
# ======================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"GLOBALER FEHLER: {exc}")
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