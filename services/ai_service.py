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
import time
from dotenv import load_dotenv

load_dotenv()

from services import umgebung

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


def _to_config(generation_config, tools=None):
    """Mappt das alte `generation_config`-Dict auf types.GenerateContentConfig.

    `tools` sind Python-Funktionen, die das Modell selbst aufrufen darf
    (automatic function calling) -- damit holt es sich Fakten, statt sie zu raten.
    """
    if not generation_config and not tools:
        return None
    if isinstance(generation_config, dict) or generation_config is None:
        werte = dict(generation_config or {})
        if tools:
            werte["tools"] = list(tools)
        return types.GenerateContentConfig(**werte)
    return generation_config


def _extract_usage(response):
    """Liest Tokenzahlen aus der Antwort, falls das SDK sie mitliefert."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None, None
    prompt_tokens = getattr(usage, "prompt_token_count", None)
    antwort_tokens = getattr(usage, "candidates_token_count", None)
    gesamt = getattr(usage, "total_token_count", None)
    if gesamt is None and (prompt_tokens or antwort_tokens):
        gesamt = (prompt_tokens or 0) + (antwort_tokens or 0)
    return prompt_tokens, antwort_tokens, gesamt


def _tatsaechliches_modell(response, angefragt: str) -> str:
    """Welches Modell wirklich geantwortet hat -- und damit abgerechnet wurde.

    Angefragt wird ein Alias ("gemini-flash-latest"), weil fest versionierte
    Namen für neue Schlüssel wegbrechen können. Google zeigt den Alias aber
    laufend auf neuere Modelle um: in der Abrechnung tauchten dadurch Gemini
    2.5 Flash, 3.5 Flash Lite, 3.6 Flash und 3.7 Flash nebeneinander auf.

    Wer im Protokoll nur den Alias stehen hat, kann die Kosten hinterher
    keinem Modell zuordnen -- und merkt auch nicht, wenn ein Umschwenken den
    Preis ändert. Deshalb wird die konkrete Fassung aus der Antwort
    festgehalten, sofern das SDK sie mitliefert.
    """
    return getattr(response, "model_version", None) or angefragt


def _beschreibe_fehler(e: Exception) -> str:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    status = getattr(e, "status", None)
    message = getattr(e, "message", None) or str(e)
    return f"http_status={code} status={status}: {message}"


class _GeminiModel:
    """Dünner Adapter, der die bisherige `.generate_content(...)`-Schnittstelle
    (inkl. `response.text`) auf das neue google-genai SDK abbildet. So bleiben
    alle Aufrufstellen (Judge, Scanner, Deck-Analyse/Roast, Kartenübersetzung,
    Vision) unverändert.

    Zusätzlich:
    - Ersatzmodell: Fällt das Hauptmodell aus (z.B. 404 abgeschaltetes Modell,
      503 Überlastung), wird EINMAL mit dem Ersatzmodell wiederholt, statt die
      Funktion für den Nutzer ausfallen zu lassen.
    - Protokoll: Modell, Tokens, Latenz, Kosten und Erfolg jeder Anfrage werden
      erfasst (gepuffert, ohne die Antwort zu verzögern).
    """

    def __init__(self, client, model_name: str, fallback_model_name: str = None):
        self._client = client
        self._model = model_name
        self._fallback_model = fallback_model_name

    def _aufruf(self, model_name, contents, generation_config, tools):
        return self._client.models.generate_content(
            model=model_name,
            contents=_normalize_contents(contents),
            config=_to_config(generation_config, tools),
        )

    def generate_content(self, contents, generation_config=None, feature="unbekannt",
                         benutzername=None, tools=None):
        # Modellkette: Hauptmodell, danach (falls konfiguriert und abweichend)
        # das Ersatzmodell.
        kette = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            kette.append(self._fallback_model)

        letzter_fehler = None
        for index, model_name in enumerate(kette):
            start = time.perf_counter()
            try:
                response = self._aufruf(model_name, contents, generation_config, tools)
            except Exception as e:
                dauer_ms = int((time.perf_counter() - start) * 1000)
                letzter_fehler = e
                beschreibung = _beschreibe_fehler(e)
                logger.warning("Gemini-Aufruf fehlgeschlagen (model=%s): %s", model_name, beschreibung)
                _protokolliere(
                    funktion=feature, modell=model_name, erfolg=False,
                    latenz_ms=dauer_ms, fehler=beschreibung, benutzername=benutzername,
                    frage=_als_text(contents),
                )
                if index + 1 < len(kette):
                    logger.info("Wechsle auf Ersatzmodell %s.", kette[index + 1])
                continue

            dauer_ms = int((time.perf_counter() - start) * 1000)
            prompt_tokens, antwort_tokens, gesamt = _extract_usage(response)
            _protokolliere(
                funktion=feature, modell=_tatsaechliches_modell(response, model_name),
                erfolg=True, latenz_ms=dauer_ms,
                prompt_tokens=prompt_tokens, antwort_tokens=antwort_tokens,
                gesamt_tokens=gesamt, benutzername=benutzername,
                frage=_als_text(contents), antwort=getattr(response, "text", None),
            )
            if index > 0:
                logger.info("Ersatzmodell %s hat die Anfrage beantwortet.", model_name)
            return response

        raise letzter_fehler


def _als_text(contents):
    """Reduziert `contents` auf reinen Text (Bilddaten werden nie protokolliert)."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, (list, tuple)):
        return "\n".join(c for c in contents if isinstance(c, str)) or None
    return None


def _protokolliere(**kwargs):
    """Schreibt einen Protokolleintrag; Fehler dabei dürfen die KI nie stören."""
    try:
        from services.ai_usage_log import record
        record(**kwargs)
    except Exception:
        logger.debug("KI-Protokolleintrag fehlgeschlagen", exc_info=True)


# --- Modelle initialisieren (Kosten-Tiering, siehe KI-Kosten-Audit) ---
# - model       -> Deck-Analyse (komplexes JSON-Schema, Anti-Halluzination).
# - model_lite  -> alles andere (Judge, Übersetzung, Roast, Combo-Fallbacks, Vision).
#
# Default sind Googles rollende Alias-Modelle ("...-latest"): Google schaltet
# fest versionierte Modelle für neue API-Keys ab (z.B. gab 'gemini-2.5-flash'
# HTTP 404 "no longer available to new users") -- die -latest-Aliase zeigen
# hingegen immer auf das aktuelle Modell und brechen darum nicht weg.
# Ein bestimmtes Modell lässt sich per GEMINI_MODEL / GEMINI_MODEL_LITE in der
# .env erzwingen (z.B. gemini-2.0-flash oder gemini-3-flash-preview).
#
# umgebung.text statt os.getenv: eine LEERE Zeile "GEMINI_MODEL=" in der .env
# muss den Standard ergeben, nicht "". os.getenv liefert den Standard nur bei
# einer gar nicht vorhandenen Variable -- mit einem leeren Modellnamen
# scheiterte jeder KI-Aufruf mit "model is required", noch bevor überhaupt eine
# Anfrage an Google ging.
MODEL_NAME = umgebung.text("GEMINI_MODEL", "gemini-flash-latest")
MODEL_LITE_NAME = umgebung.text("GEMINI_MODEL_LITE", "gemini-flash-lite-latest")

# Ersatzmodelle: Fällt das Hauptmodell aus (abgeschaltetes Modell, Überlastung,
# regionale Störung), wird EINMAL mit diesem Modell wiederholt. Standardmäßig
# stützt sich das teure Modell auf das günstige und umgekehrt -- so bleibt die
# Funktion verfügbar, statt für den Nutzer komplett auszufallen.
MODEL_FALLBACK_NAME = umgebung.text("GEMINI_MODEL_FALLBACK", MODEL_LITE_NAME)
MODEL_LITE_FALLBACK_NAME = umgebung.text("GEMINI_MODEL_LITE_FALLBACK", MODEL_NAME)

model = None
model_lite = None
# roh() statt getenv: schneidet Randleerzeichen ab. Ein beim Kopieren
# mitgenommenes Leerzeichen im Schlüssel führt sonst zu "API key not valid" --
# einem Fehler, den man an der richtig aussehenden .env-Zeile nicht sieht.
api_key = umgebung.roh(GEMINI_API_KEY_ENV)

if KI_VERFUEGBAR and api_key:
    try:
        # api_key=... spricht den nativen Gemini Developer API-Endpoint an
        # (generativelanguage.googleapis.com), passend für AIza- UND AQ.-Keys.
        client = genai.Client(api_key=api_key)
        model = _GeminiModel(client, MODEL_NAME, MODEL_FALLBACK_NAME)
        model_lite = _GeminiModel(client, MODEL_LITE_NAME, MODEL_LITE_FALLBACK_NAME)
        logger.info(
            "Gemini (google-genai SDK) initialisiert: %s (Ersatz: %s) / %s (Ersatz: %s).",
            MODEL_NAME, MODEL_FALLBACK_NAME, MODEL_LITE_NAME, MODEL_LITE_FALLBACK_NAME,
        )
    except Exception:
        logger.exception("FEHLER beim Initialisieren des Gemini-Clients")
elif KI_VERFUEGBAR and not api_key:
    logger.warning(
        "%s ist nicht gesetzt -- KI-Funktionen (Judge, Scanner, Analyse) sind deaktiviert.",
        GEMINI_API_KEY_ENV,
    )


# ======================================================================
# Modellwahl je Funktion
# ======================================================================
def modell_fuer(funktion: str):
    """Das Modell, auf dem diese Funktion laufen soll.

    Die Zuordnung steht in services/ki_modelle.py -- an einer Stelle,
    nachlesbar und je Funktion per Umgebungsvariable umstellbar. Vorher
    entschied jede Aufrufstelle selbst, indem sie `model` oder `model_lite`
    importierte; welche Funktion das teure Modell benutzt, liess sich dadurch
    nur durch Quelltextlesen beantworten.

    Gibt None zurück, wenn keine KI eingerichtet ist -- die Aufrufstellen
    prüfen darauf ohnehin schon, weil die Anwendung ohne Schlüssel
    weiterlaufen muss.
    """
    from services.ki_modelle import GROSS, stufe_fuer

    return model if stufe_fuer(funktion) == GROSS else model_lite
