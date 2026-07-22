"""
services/ai_service.py – Gemini KI-Model Wrapper

Kapselt die Initialisierung und den Zugriff auf die Gemini-Modelle.
Andere Module importieren `model`, `model_lite` und `KI_VERFUEGBAR` von hier.

Nutzt das AKTUELLE, native google-genai SDK (`from google import genai`), das
den nativen generativelanguage-Endpoint anspricht -- KEIN OpenAI-kompatibler Shim.
Das ist wichtig für die neuen AI-Studio-Keys mit Präfix "AQ." (statt "AIza"):
der OpenAI-Shim quittiert AQ.-Keys mit "Multiple authentication credentials
received". Es gibt bewusst KEINE Key-Format-Validierung -- jeder von Google
ausgegebene Key (AIza… oder AQ.…) wird unverändert an das SDK durchgereicht.

Der Key kommt ausschließlich aus der Umgebungsvariable GEMINI_API_KEY (nie
hartcodiert). Judge und Synergie-Scanner nutzen dieselbe Variable, da beide
`model`/`model_lite` von hier importieren.
"""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Name der Umgebungsvariable mit dem Gemini-API-Key (zentral, damit Judge und
# Scanner garantiert denselben Key verwenden).
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"

# --- Sicherer Import des nativen google-genai SDK ---
try:
    from google import genai
    from google.genai import types
    KI_VERFUEGBAR = True
except ImportError:
    logger.warning(
        "Das Modul 'google-genai' fehlt! Bitte installieren: pip install google-genai"
    )
    genai = None
    types = None
    KI_VERFUEGBAR = False


def _normalize_contents(contents):
    """Wandelt die von den Aufrufstellen übergebenen `contents` in das Format des
    neuen SDK. Strings bleiben Strings; alte multimodale Dicts
    ({"mime_type": ..., "data": bytes}) werden zu types.Part.from_bytes."""
    if isinstance(contents, (list, tuple)):
        parts = []
        for item in contents:
            if isinstance(item, dict) and "data" in item and "mime_type" in item:
                parts.append(types.Part.from_bytes(data=item["data"], mime_type=item["mime_type"]))
            else:
                parts.append(item)
        return parts
    return contents


def _to_config(generation_config):
    """Mappt das alte `generation_config`-Dict auf types.GenerateContentConfig."""
    if not generation_config:
        return None
    if isinstance(generation_config, dict):
        return types.GenerateContentConfig(**generation_config)
    return generation_config


class _GeminiModel:
    """Dünner Adapter, der die bisherige `.generate_content(...)`-Schnittstelle
    (inkl. `response.text`) auf das neue google-genai SDK abbildet. So bleiben
    alle Aufrufstellen (Judge, Scanner, Deck-Analyse/Roast, Kartenübersetzung,
    Vision) unverändert."""

    def __init__(self, client, model_name: str):
        self._client = client
        self._model = model_name

    def generate_content(self, contents, generation_config=None):
        try:
            return self._client.models.generate_content(
                model=self._model,
                contents=_normalize_contents(contents),
                config=_to_config(generation_config),
            )
        except Exception as e:
            # Echten Gemini-Statuscode/Meldung loggen, damit die Ursache (z.B.
            # 400 ungültiger Key, 403 Key ohne Zugriff, 429 Quota) sichtbar ist.
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            status = getattr(e, "status", None)
            message = getattr(e, "message", None) or str(e)
            logger.warning(
                "Gemini-Aufruf fehlgeschlagen (model=%s, http_status=%s, status=%s): %s",
                self._model, code, status, message,
            )
            raise


# --- Modelle initialisieren (Kosten-Tiering, siehe KI-Kosten-Audit) ---
# - model       -> Deck-Analyse (komplexes JSON-Schema, Anti-Halluzination).
# - model_lite  -> alles andere (Judge, Übersetzung, Roast, Combo-Fallbacks, Vision).
#
# Die Modellnamen sind über Umgebungsvariablen überschreibbar, weil Google
# einzelne Modelle abschaltet (z.B. war 'gemini-2.5-flash-lite' für neue
# API-Keys nicht mehr verfügbar -> HTTP 404 NotFound). Default ist deshalb für
# beide Stufen das breit verfügbare gemini-2.5-flash; wer flash-lite nutzen
# kann, setzt GEMINI_MODEL_LITE=gemini-2.5-flash-lite in der .env.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODEL_LITE_NAME = os.getenv("GEMINI_MODEL_LITE", "gemini-2.5-flash")

model = None
model_lite = None
api_key = os.getenv(GEMINI_API_KEY_ENV)

if KI_VERFUEGBAR and api_key:
    try:
        # api_key=... spricht den nativen Gemini Developer API-Endpoint an
        # (generativelanguage.googleapis.com), passend für AIza- UND AQ.-Keys.
        client = genai.Client(api_key=api_key)
        model = _GeminiModel(client, MODEL_NAME)
        model_lite = _GeminiModel(client, MODEL_LITE_NAME)
        logger.info("Gemini (google-genai SDK) initialisiert: %s / %s.", MODEL_NAME, MODEL_LITE_NAME)
    except Exception:
        logger.exception("FEHLER beim Initialisieren des Gemini-Clients")
elif KI_VERFUEGBAR and not api_key:
    logger.warning(
        "%s ist nicht gesetzt -- KI-Funktionen (Judge, Scanner, Analyse) sind deaktiviert.",
        GEMINI_API_KEY_ENV,
    )
