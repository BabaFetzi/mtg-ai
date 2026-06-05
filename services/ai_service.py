"""
services/ai_service.py – Gemini KI-Model Wrapper

Kapselt die Initialisierung und den Zugriff auf das Gemini-Modell.
Andere Module importieren `model` und `KI_VERFUEGBAR` von hier.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Sicherer KI-Import ---
try:
    import google.generativeai as genai
    KI_VERFUEGBAR = True
except ImportError:
    print("\n" + "=" * 60)
    print("WARNUNG: Das Modul 'google-generativeai' fehlt!")
    print("Bitte führe im Terminal diesen Befehl aus: pip install google-generativeai")
    print("=" * 60 + "\n")
    genai = None
    KI_VERFUEGBAR = False

# --- API Client initialisieren ---
model = None
api_key = os.getenv("GEMINI_API_KEY")

if KI_VERFUEGBAR and api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        print("INFO: Gemini KI-Modell erfolgreich initialisiert.")
    except Exception as e:
        print(f"FEHLER beim Initialisieren der KI: {e}")
