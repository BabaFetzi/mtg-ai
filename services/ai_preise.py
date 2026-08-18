"""services/ai_preise.py -- was ein Modell je Million Tokens kostet.

Warum je Modell und nicht ein Preis für alles
---------------------------------------------
Die Anwendung benutzt zwei Modelle: das grosse für die Deck-Analyse, das
kleine für alles andere. Zwischen den Modellen liegen Welten -- laut
Preisliste kostet die Ausgabe bei Gemini 2.5 Flash-Lite 0,40 USD je Million
Tokens, bei Gemini 3.5 Flash 9,00 USD. Das ist Faktor 22.

Mit einem einzigen Preis für alles wäre jede Kostenrechnung entweder deutlich
zu hoch oder deutlich zu niedrig. Und "zu niedrig" ist genau die Richtung, in
die man sich bei einem Abo-Geschäft nicht irren darf.

Geschlüsselt wird nach dem Modell, das TATSÄCHLICH geantwortet hat (siehe
services/ai_service._tatsaechliches_modell). Angefragt wird nämlich ein Alias
("gemini-flash-latest"), und Google zeigt den laufend auf neuere Modelle um.

Konfiguration
-------------
    GEMINI_PREISE=gemini-2.5-flash:0.30/2.50; gemini-2.5-flash-lite:0.10/0.40

Je Eintrag ``modell:eingabe/ausgabe`` -- Preis je 1 Mio. Tokens. Getrennt wird
mit **Semikolon** (oder Zeilenumbruch), NICHT mit Komma: das Komma ist das
deutsche Dezimalzeichen, und "0,30" darf nicht als zwei Einträge zerfallen.
Leerzeichen sind egal.

Ein Modell ohne Eintrag bekommt KEINEN Preis. Es wird als unbekannt
ausgewiesen, statt still mit einem falschen Wert zu rechnen: dass ein Alias
plötzlich auf ein Modell zeigt, dessen Preis niemand hinterlegt hat, ist genau
der Fall, den man sehen will. (Bei Grana stand in der Abrechnung ein
"Gemini 3.7 Flash", das auf der Preisseite gar nicht vorkam.)

Altbestand
----------
GEMINI_PRICE_INPUT_PER_MTOK und GEMINI_PRICE_OUTPUT_PER_MTOK gelten weiter --
sie zählen als Eintrag für "*", also als Preis für jedes Modell ohne eigenen
Eintrag. Wer nur ein Modell benutzt, muss nichts umstellen.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Preis für jedes Modell, das keinen eigenen Eintrag hat.
ALLGEMEIN = "*"


def _zahl(roh: Optional[str]) -> Optional[float]:
    """Liest eine Zahl, auch mit Komma -- so steht sie auf deutschen Seiten."""
    if roh is None:
        return None
    roh = roh.strip().replace(",", ".")
    if not roh:
        return None
    try:
        wert = float(roh)
    except ValueError:
        return None
    return wert if wert >= 0 else None


def tabelle() -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Modellname -> (Eingabepreis, Ausgabepreis) je 1 Mio. Tokens.

    Wird bei jedem Aufruf neu gelesen, damit eine Preisänderung ohne Neustart
    wirkt -- und damit Tests die Umgebung setzen können.
    """
    preise: Dict[str, Tuple[Optional[float], Optional[float]]] = {}

    # Semikolon und Zeilenumbruch trennen Eintraege -- das Komma NICHT, es ist
    # das deutsche Dezimalzeichen. Wer "0,30" schreibt, darf davon nicht zwei
    # kaputte Eintraege bekommen.
    roh_eintraege = (os.getenv("GEMINI_PREISE") or "").replace("\n", ";").split(";")
    for eintrag in roh_eintraege:
        eintrag = eintrag.strip()
        if not eintrag:
            continue
        modell, _, rest = eintrag.rpartition(":")
        if not modell or "/" not in rest:
            logger.warning("GEMINI_PREISE: Eintrag %r nicht lesbar. Erwartet wird "
                           "modell:eingabe/ausgabe, mehrere Eintraege mit "
                           "Semikolon getrennt.", eintrag)
            continue
        ein, _, aus = rest.partition("/")
        preise[modell.strip().lower()] = (_zahl(ein), _zahl(aus))

    # Altbestand: ein Preis für alles.
    alt_ein = _zahl(os.getenv("GEMINI_PRICE_INPUT_PER_MTOK"))
    alt_aus = _zahl(os.getenv("GEMINI_PRICE_OUTPUT_PER_MTOK"))
    if (alt_ein is not None or alt_aus is not None) and ALLGEMEIN not in preise:
        preise[ALLGEMEIN] = (alt_ein, alt_aus)

    return preise


def preis_fuer(modell: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Preise für dieses Modell, sonst der allgemeine Preis, sonst nichts."""
    preise = tabelle()
    if modell:
        eigen = preise.get(modell.strip().lower())
        if eigen:
            return eigen
    return preise.get(ALLGEMEIN, (None, None))


def kosten(prompt_tokens: Optional[int], antwort_tokens: Optional[int],
           modell: Optional[str] = None) -> Optional[float]:
    """Kosten eines Aufrufs, oder None wenn für dieses Modell kein Preis
    hinterlegt ist.

    None heisst ausdrücklich "unbekannt", nicht "kostenlos". Ein geratener
    Preis wäre schlimmer als gar keiner.
    """
    preis_ein, preis_aus = preis_fuer(modell)
    if preis_ein is None and preis_aus is None:
        return None

    summe = 0.0
    if preis_ein is not None and prompt_tokens:
        summe += (prompt_tokens / 1_000_000) * preis_ein
    if preis_aus is not None and antwort_tokens:
        summe += (antwort_tokens / 1_000_000) * preis_aus
    return round(summe, 6)
