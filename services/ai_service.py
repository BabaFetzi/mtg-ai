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
# - model       (gemini-2.5-flash)      -> nur für Deck-Analyse, die einzige Aufgabe
#                                          mit komplexem 8-Felder-JSON-Schema und
#                                          expliziter Anti-Halluzinations-Anforderung.
# - model_lite  (gemini-2.5-flash-lite) -> Standard für alles andere (Judge,
#                                          Kartenübersetzung, Deck-Roast, Combo-Fallbacks,
#                                          Vision) -- kurze/einfache Aufgaben, hohe
#                                          Aufruffrequenz, ~6-7x günstiger.
model = None
model_lite = None
api_key = os.getenv("GEMINI_API_KEY")

if KI_VERFUEGBAR and api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        model_lite = genai.GenerativeModel('gemini-2.5-flash-lite')
        logger.info("Gemini KI-Modelle (flash, flash-lite) erfolgreich initialisiert.")
    except Exception:
        logger.exception("FEHLER beim Initialisieren der KI")
