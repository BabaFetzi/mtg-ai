"""services/umgebung.py -- Umgebungsvariablen lesen, ohne dass Leerwerte kippen.

Warum es dieses Modul gibt
--------------------------
``os.getenv("GEMINI_MODEL", "gemini-flash-latest")`` liefert den Standardwert
nur, wenn die Variable **gar nicht existiert**. Steht sie in der ``.env`` und
ist leer::

    GEMINI_MODEL=

dann kommt ``""`` zurueck -- nicht der Standard. Genau das ist bei Grana
passiert: nach dem Leeren der beiden Modellvariablen scheiterte jeder einzelne
KI-Aufruf mit "model is required", weil ein leerer Modellname an Google ging.

Der Fall ist kein Einzelfall, sondern die Regel: ``.env.example`` listet jede
Variable auf, die meisten ohne Wert. Wer die Datei kopiert, hat damit ein
Dutzend leerer, aber **vorhandener** Variablen -- und bekommt ueberall dort
``""`` statt des Standards. Bei ``DATABASE_URL`` heisst das: die Anwendung
startet nicht (``create_async_engine("")``). Bei ``int(os.getenv("SMTP_PORT",
"587"))`` heisst es: ``ValueError`` schon beim Import. Bei ``GRANA_ENV`` heisst
es, dass der Produktionsmodus samt seiner Pflichtpruefung fuer JWT_SECRET_KEY
still ausbleibt.

Deshalb wird hier einmal zentral festgelegt: **leer heisst nicht gesetzt.**

Unlesbare Werte
---------------
Eine Zahl, die keine ist (``SMTP_PORT=fuenfhundert``), ist etwas anderes als
ein Leerwert -- das ist ein echter Konfigurationsfehler. Er wird laut ins
Protokoll geschrieben, mit Namen, falschem Wert und dem stattdessen benutzten
Standard. Abgebrochen wird trotzdem nicht: ein einzelner Tippfehler in einer
Nebensaechlichkeit darf nicht die ganze Seite fuer alle Nutzer abschalten.

Gelesen wird bei jedem Aufruf neu. Wer einen Wert beim Import in eine Konstante
legt, friert ihn dort ein -- das ist die Entscheidung der aufrufenden Stelle.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Was als "ja" gilt. Bewusst grosszuegig, weil in einer .env erfahrungsgemaess
# alles davon vorkommt.
_JA = {"1", "true", "yes", "on", "ja", "wahr"}
_NEIN = {"0", "false", "no", "off", "nein", "falsch"}


def roh(name: str) -> Optional[str]:
    """Der Wert ohne Randleerzeichen, oder None wenn leer bzw. nicht gesetzt.

    Das ist der Kern des Moduls: leer und nicht gesetzt werden gleich
    behandelt.
    """
    wert = os.getenv(name)
    if wert is None:
        return None
    wert = wert.strip()
    return wert or None


def text(name: str, standard: str = "") -> str:
    """Zeichenkette, sonst der Standard."""
    return roh(name) or standard


def ganzzahl(name: str, standard: int) -> int:
    """Ganze Zahl, sonst der Standard."""
    wert = roh(name)
    if wert is None:
        return standard
    try:
        return int(wert)
    except ValueError:
        _unlesbar(name, wert, standard, "ganze Zahl")
        return standard


def zahl(name: str, standard: float) -> float:
    """Kommazahl, sonst der Standard. Ein deutsches Komma wird akzeptiert."""
    wert = roh(name)
    if wert is None:
        return standard
    try:
        return float(wert.replace(",", "."))
    except ValueError:
        _unlesbar(name, wert, standard, "Zahl")
        return standard


def schalter(name: str, standard: bool) -> bool:
    """An/Aus, sonst der Standard.

    Ein unbekannter Wert schaltet NICHT stillschweigend um -- er behaelt den
    Standard und wird gemeldet. "MULTILANG_SEARCH_ENABLED=vielleicht" darf
    keine Funktion abschalten, ohne dass jemand davon erfaehrt.
    """
    wert = roh(name)
    if wert is None:
        return standard
    klein = wert.lower()
    if klein in _JA:
        return True
    if klein in _NEIN:
        return False
    _unlesbar(name, wert, standard, "true oder false")
    return standard


def _unlesbar(name: str, wert: str, standard, erwartet: str) -> None:
    logger.error(
        "%s=%r ist keine %s -- der Wert wird ignoriert, benutzt wird %r. "
        "Bitte in der .env korrigieren.",
        name, wert, erwartet, standard,
    )
