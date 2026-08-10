"""
services/multilingual_search.py – Kartensuche in beliebiger Sprache

Problem: Für brandneue Sets gibt es die lokalisierten Kartennamen noch nirgends.
Geprüft am Hobbit-Set (Release 14.08.2026): Scryfall hat KEINE deutschen Drucke,
MTGJSON ebenfalls nicht (360 Karten, 0 Übersetzungen). Eine Nachschlagetabelle
kann es also nicht geben -- die Daten existieren schlicht noch nicht.

Lösung: Das Sprachmodell schlägt englische Namen vor, und Scryfall BESTÄTIGT sie.

    "Furchterregendes Goblin-Duo"
      -> Modell schlägt vor: "Fearsome Goblin Duo", "Terrifying Goblin Pair", ...
      -> Scryfall-Fuzzy bestätigt: "Fearsome Goblin Pair"   <- echte Karte

Entscheidend für die Verlässlichkeit: Der Vorschlag des Modells wird NIE direkt
angezeigt. Nur was Scryfall als real existierende Karte bestätigt, zählt.
Halluziniert das Modell, findet Scryfall nichts und es passiert genau nichts.
Damit kann diese Stufe keine falschen Karten erzeugen -- der Fehler, der früher
zu einer gar nicht besessenen Karte im Combo-Ergebnis führte.

Kosten: Ein günstiger Modellaufruf, und zwar nur, wenn alle anderen Wege
gescheitert sind. Das Ergebnis wird dauerhaft zwischengespeichert (auch das
negative), sodass derselbe Name nie zweimal übersetzt wird.
"""

import asyncio
import json
import logging
import os
import re
import urllib.parse
from typing import List, Optional

from services.cache import scryfall_cache
from services.scryfall import scryfall_request

logger = logging.getLogger(__name__)

# Abschaltbar, falls die Übersetzungsstufe einmal mehr kosten als nützen sollte.
UEBERSETZUNGSSUCHE_AKTIV = os.getenv("MULTILANG_SEARCH_ENABLED", "true").strip().lower() not in {
    "0", "false", "no", "off"
}

MAX_KANDIDATEN = int(os.getenv("MULTILANG_MAX_CANDIDATES", "5"))

# Cache-Version im Schlüssel: erlaubt es, alte Zuordnungen bei einer
# Verbesserung des Verfahrens gezielt ungültig zu machen.
_CACHE_PRAEFIX = "namemap:v1:"


def _wirkt_wie_kartenname(begriff: str) -> bool:
    """Grobfilter gegen sinnlose Eingaben, bevor ein Modellaufruf entsteht.

    Ein Kartenname besteht aus Buchstaben und ist entweder mehrteilig oder
    hinreichend lang. Tippfehler wie "xyz" lösen so keinen Aufruf aus.
    """
    text = (begriff or "").strip()
    if len(text) < 4 or len(text) > 80:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]{3}", text):
        return False
    # Mindestens zwei Wörter ODER ein längeres Einzelwort
    return " " in text or "-" in text or len(text) >= 8


async def _frage_modell_nach_englischen_namen(begriff: str) -> List[str]:
    """Lässt das Modell mögliche englische Kartennamen vorschlagen."""
    from services.ai_service import model_lite

    if model_lite is None:
        return []

    prompt = (
        "Du hilfst, einen Magic-the-Gathering-Kartennamen zu identifizieren.\n"
        f"Eingabe (irgendeine gedruckte Sprache, oft Deutsch): \"{begriff}\"\n\n"
        "Nenne die wahrscheinlichsten ENGLISCHEN Kartennamen dazu.\n"
        "- Kennst du den offiziellen englischen Namen, nenne ihn zuerst.\n"
        "- Kennst du ihn nicht (z.B. sehr neue Karte), gib möglichst wörtliche "
        "Übersetzungen an, auch mit alternativen Wortwahlen "
        "(z.B. Duo/Pair, Ruin/Downfall/Doom).\n"
        "- Ist die Eingabe bereits Englisch, gib sie unverändert zurück.\n\n"
        f"Antworte AUSSCHLIESSLICH als JSON: {{\"namen\": [\"...\", \"...\"]}} "
        f"mit höchstens {MAX_KANDIDATEN} Einträgen, ohne Markdown."
    )

    try:
        antwort = await asyncio.to_thread(
            model_lite.generate_content, prompt, None, "kartenname_uebersetzung", None
        )
        roh = (getattr(antwort, "text", "") or "").strip()
    except Exception:
        logger.warning("Namensübersetzung: Modellaufruf fehlgeschlagen", exc_info=True)
        return []

    treffer = re.search(r"\{.*\}", roh, re.DOTALL)
    if not treffer:
        return []
    try:
        namen = json.loads(treffer.group(0)).get("namen", [])
    except (ValueError, AttributeError):
        return []

    sauber = []
    for name in namen:
        if isinstance(name, str) and 2 <= len(name.strip()) <= 80:
            sauber.append(name.strip())
    return sauber[:MAX_KANDIDATEN]


async def _bestaetige_bei_scryfall(client, kandidat: str) -> Optional[dict]:
    """Prüft EINEN Vorschlag gegen Scryfall. Nur ein echter Treffer zählt."""
    try:
        url = "https://api.scryfall.com/cards/named?fuzzy=" + urllib.parse.quote(kandidat)
        resp = await scryfall_request(client, "GET", url)
    except Exception:
        logger.debug("Bestätigung fehlgeschlagen für %r", kandidat, exc_info=True)
        return None
    if resp.status_code == 200:
        return resp.json()
    return None


async def finde_karte_sprachunabhaengig(client, begriff: str) -> Optional[dict]:
    """
    Letzte Suchstufe: Kartenname in beliebiger Sprache -> bestätigte Karte.

    Args:
        client: offener httpx-AsyncClient (Scryfall).
        begriff: Eingabe des Nutzers in beliebiger Sprache.

    Returns:
        Das vollständige Scryfall-Kartenobjekt, oder None wenn nichts bestätigt
        werden konnte. Es wird NIEMALS ein unbestätigter Vorschlag geliefert.
    """
    if not UEBERSETZUNGSSUCHE_AKTIV or not _wirkt_wie_kartenname(begriff):
        return None

    schluessel = _CACHE_PRAEFIX + begriff.lower().strip()
    gemerkt = scryfall_cache.get(schluessel)
    if gemerkt is not None:
        # "" = bekannt: dafür gibt es keine Entsprechung (kein erneuter Modellaufruf)
        if not gemerkt:
            return None
        return await _bestaetige_bei_scryfall(client, gemerkt)

    kandidaten = await _frage_modell_nach_englischen_namen(begriff)
    if not kandidaten:
        return None

    for kandidat in kandidaten:
        karte = await _bestaetige_bei_scryfall(client, kandidat)
        if karte:
            logger.info(
                "Sprachunabhängige Suche: %r -> %r (über Vorschlag %r bestätigt)",
                begriff, karte.get("name"), kandidat,
            )
            # Zuordnung merken: derselbe Name kostet nie wieder einen Modellaufruf.
            scryfall_cache.set(schluessel, karte.get("name", ""))
            return karte

    # Auch das negative Ergebnis merken -- verhindert wiederholte Modellaufrufe
    # für denselben erfolglosen Begriff.
    scryfall_cache.set(schluessel, "")
    return None
