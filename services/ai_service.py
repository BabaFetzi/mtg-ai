"""
services/ai_service.py – Gemini KI-Model Wrapper

Kapselt die Initialisierung und den Zugriff auf das Gemini-Modell.
Andere Module importieren `model` und `KI_VERFUEGBAR` von hier.
"""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Sicherer KI-Import ---
try:
    import google.generativeai as genai
    KI_VERFUEGBAR = True
except ImportError:
    logger.warning(
        "Das Modul 'google-generativeai' fehlt! Bitte im Terminal ausführen: "
        "pip install google-generativeai"
    )
    genai = None
    KI_VERFUEGBAR = False

# --- API Client initialisieren ---
# Zwei Modell-Stufen (Kosten-Tiering, siehe KI-Kosten-Audit):
# - model       -> Deck-Analyse (komplexes 8-Felder-JSON-Schema, Anti-Halluzination).
# - model_lite  -> alles andere (Judge, Kartenübersetzung, Deck-Roast, Combo-Fallbacks,
#                  Vision) -- kurze/einfache Aufgaben, hohe Aufruffrequenz.
#
# Die Modellnamen sind über Umgebungsvariablen überschreibbar, weil Google
# einzelne Modelle abschaltet (z.B. war 'gemini-2.5-flash-lite' für neue
# API-Keys nicht mehr verfügbar -> HTTP 404). Bei einem 404/NotFound in den
# Logs einfach GEMINI_MODEL / GEMINI_MODEL_LITE in der .env auf ein aktuelles
# Modell setzen, ohne Code-Änderung.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODEL_LITE_NAME = os.getenv("GEMINI_MODEL_LITE", "gemini-2.5-flash")

model = None
model_lite = None
api_key = os.getenv("GEMINI_API_KEY")

if KI_VERFUEGBAR and api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        model_lite = genai.GenerativeModel(MODEL_LITE_NAME)
        logger.info("Gemini KI-Modelle initialisiert (%s / %s).", MODEL_NAME, MODEL_LITE_NAME)
    except Exception:
        logger.exception("FEHLER beim Initialisieren der KI")
