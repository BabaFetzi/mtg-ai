"""
services/card_query_tool.py – Kartensuche als Werkzeug für das Modell

Das ist die Grana-Umsetzung von "strukturierte Daten gehören in ein Werkzeug,
nicht in eine Ähnlichkeitssuche".

Wichtig: Grana braucht dafür KEINE eigene Kartendatenbank. Scryfall ist bereits
die exakt abfragbare Datenbank und beherrscht eine vollwertige Suchsyntax
(`t:creature c:u cmc<3 o:flying f:standard`). Das Werkzeug reicht diese Syntax
durch -- ein eigener Index oder Embeddings wären langsamer, teurer und
ungenauer.

Die Funktion ist bewusst SYNCHRON: Das Gemini-SDK ruft Werkzeuge selbst auf
(automatic function calling), und der Modellaufruf läuft ohnehin in einem
eigenen Thread, damit er den Event-Loop nicht blockiert.
"""

import logging
import os
import threading
import time
from typing import Any, Dict

import httpx

from services.cache import scryfall_cache
from services.scryfall import SCRYFALL_HEADERS

logger = logging.getLogger(__name__)

# Höchstzahl zurückgegebener Karten: genug Kontext für eine Antwort, ohne den
# Prompt (und damit die Kosten) aufzublähen.
MAX_ERGEBNISSE = int(os.getenv("CARD_TOOL_MAX_RESULTS", "10"))
CARD_TOOL_TIMEOUT = float(os.getenv("CARD_TOOL_TIMEOUT", "8"))

# Einfache synchrone Drossel. Der asynchrone Scryfall-Limiter greift hier nicht,
# weil dieser Aufruf aus einem Worker-Thread des SDK kommt.
_MIN_INTERVAL = float(os.getenv("CARD_TOOL_MIN_INTERVAL", "0.15"))
_lock = threading.Lock()
_next_slot = 0.0


def _drossel() -> None:
    global _next_slot
    with _lock:
        jetzt = time.monotonic()
        start = max(jetzt, _next_slot)
        _next_slot = start + _MIN_INTERVAL
        wartezeit = start - jetzt
    if wartezeit > 0:
        time.sleep(wartezeit)


def karten_suchen(suchanfrage: str) -> Dict[str, Any]:
    """Sucht Magic-Karten anhand der Scryfall-Suchsyntax.

    Nutze dieses Werkzeug, wenn nach Karten mit bestimmten Eigenschaften gefragt
    wird (Farbe, Typ, Manakosten, Regeltext, Formatlegalität) statt nach einer
    namentlich genannten Karte.

    Beispiele für suchanfrage:
      "c:u t:creature cmc<=3 o:flying f:standard"  – blaue Kreaturen bis 3 Mana mit Fliegend, Standard-legal
      "t:land o:'add one mana of any color'"       – Länder, die beliebiges Mana erzeugen
      "f:commander o:'whenever you gain life'"      – Commander-legale Karten mit Lebensgewinn-Auslöser

    Args:
        suchanfrage: Suchausdruck in Scryfall-Syntax (englisch).

    Returns:
        Dict mit 'anzahl' (Gesamttreffer), 'karten' (Liste mit name, typ,
        manakosten, regeltext) und ggf. 'hinweis'.
    """
    anfrage = (suchanfrage or "").strip()
    if not anfrage:
        return {"anzahl": 0, "karten": [], "hinweis": "Leere Suchanfrage."}

    cache_key = f"cardtool:v1:{anfrage.lower()}"
    zwischengespeichert = scryfall_cache.get(cache_key)
    if zwischengespeichert is not None:
        return zwischengespeichert

    try:
        _drossel()
        resp = httpx.get(
            "https://api.scryfall.com/cards/search",
            params={"q": anfrage, "order": "edhrec", "unique": "cards"},
            headers=SCRYFALL_HEADERS,
            timeout=CARD_TOOL_TIMEOUT,
        )
    except Exception:
        logger.warning("Kartensuche-Werkzeug: Scryfall nicht erreichbar", exc_info=True)
        return {"anzahl": 0, "karten": [], "hinweis": "Kartendatenbank momentan nicht erreichbar."}

    if resp.status_code == 404:
        # Scryfall meldet "keine Treffer" mit 404 -- das ist kein Fehler.
        ergebnis = {"anzahl": 0, "karten": [], "hinweis": "Keine Karte entspricht dieser Suche."}
        scryfall_cache.set(cache_key, ergebnis)
        return ergebnis

    if resp.status_code != 200:
        logger.warning("Kartensuche-Werkzeug: HTTP %s für %r", resp.status_code, anfrage)
        return {
            "anzahl": 0, "karten": [],
            "hinweis": "Suche fehlgeschlagen (evtl. ungültige Syntax).",
        }

    daten = resp.json()
    karten = []
    for eintrag in (daten.get("data") or [])[:MAX_ERGEBNISSE]:
        regeltext = eintrag.get("oracle_text", "")
        if not regeltext and "card_faces" in eintrag:
            regeltext = " // ".join(
                f.get("oracle_text", "") for f in eintrag["card_faces"]
            ).strip()
        karten.append({
            "name": eintrag.get("name", ""),
            "typ": eintrag.get("type_line", ""),
            "manakosten": eintrag.get("mana_cost", ""),
            "regeltext": regeltext,
        })

    ergebnis = {
        "anzahl": daten.get("total_cards", len(karten)),
        "karten": karten,
    }
    if ergebnis["anzahl"] > len(karten):
        ergebnis["hinweis"] = (
            f"Nur die ersten {len(karten)} von {ergebnis['anzahl']} Treffern werden gezeigt."
        )
    scryfall_cache.set(cache_key, ergebnis)
    return ergebnis
