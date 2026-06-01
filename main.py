from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import urllib.parse
import json
import aiosqlite
import asyncio
import hashlib
import re
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# --- SICHERER KI-IMPORT (Das war der Übeltäter!) ---
try:
    import google.generativeai as genai
    KI_VERFUEGBAR = True
except ImportError:
    print("\n" + "="*60)
    print("WARNUNG: Das Modul 'google-generativeai' fehlt!")
    print("Bitte führe im Terminal diesen Befehl aus: pip install google-generativeai")
    print("="*60 + "\n")
    genai = None
    KI_VERFUEGBAR = False

# --- UMWELTVARIABLEN LADEN ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# --- API CLIENT INITIALISIEREN ---
model = None
if KI_VERFUEGBAR and api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print(f"FEHLER beim Initialisieren der KI: {e}")

HEADERS = {
    "User-Agent": "MTGAppPro/2.0", 
    "Accept": "application/json"
}

# --- IN-MEMORY CACHE ---
KARTEN_CACHE = {}
KI_CACHE = {}

# --- DATENBANK INITIALISIERUNG ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starte Datenbankverbindung...")
    try:
        async with aiosqlite.connect('mtg_app.db') as db:
            await db.execute('CREATE TABLE IF NOT EXISTS nutzer (benutzername TEXT PRIMARY KEY, passwort_hash TEXT)')
            await db.execute('CREATE TABLE IF NOT EXISTS sammlung_alben (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, karten_name TEXT, album_name TEXT, bild_url TEXT, preis TEXT)')
            await db.execute('CREATE TABLE IF NOT EXISTS decks (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, deck_name TEXT, deck_liste TEXT)')
            await db.commit()
        print("Datenbank erfolgreich initialisiert. Backend ist BEREIT für den Login!")
    except Exception as e:
        print(f"FEHLER bei der Datenbankinitialisierung: {e}")
    yield

app = FastAPI(title="MTG App Pro Backend", lifespan=lifespan)

# --- GLOBALE FEHLERBEHANDLUNG ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"GLOBALER FEHLER: {exc}")
    return JSONResponse(status_code=500, content={"erfolg": False, "error": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean_json_response(text):
    text = text.strip()
    if text.startswith('