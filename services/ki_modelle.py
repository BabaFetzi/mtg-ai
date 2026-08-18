"""services/ki_modelle.py -- welche Funktion auf welchem Modell läuft.

Warum eine eigene Tabelle
-------------------------
Vorher stand die Zuordnung verstreut in den Routern: jede Aufrufstelle
importierte entweder ``model`` oder ``model_lite`` und traf die Entscheidung
damit nebenbei. Das hatte drei Folgen.

* Man konnte nicht nachsehen, was womit läuft. Die Antwort auf "welche
  Funktion kostet uns das teure Modell?" stand in acht verschiedenen Dateien.
* Man konnte es nicht ändern, ohne Code anzufassen -- eine Modellwahl ist aber
  eine Betriebsentscheidung, keine Programmieraufgabe.
* Man konnte es nicht messen. werkzeuge/ki_kosten.py weist die Kosten je
  Funktion aus; ohne eine Zuordnung an einer Stelle liess sich daraus keine
  Empfehlung ableiten.

Hier steht sie jetzt an genau einer Stelle, und zwar vollständig: jede
Funktion, die ein Modell benutzt, hat eine Zeile.

Stufen statt Modellnamen
------------------------
Eingetragen wird eine STUFE ("gross" / "klein"), nicht ein Modellname. Welches
Modell hinter einer Stufe steckt, sagen GEMINI_MODEL und GEMINI_MODEL_LITE.
So bleibt der Modellwechsel eine einzige Änderung, auch wenn zehn Funktionen
darauf zeigen.

Überschreiben ohne Codeänderung
-------------------------------
Je Funktion mit ``GEMINI_STUFE_<FUNKTION>``, z.B.::

    GEMINI_STUFE_DECK_ANALYSE=klein

Damit lässt sich eine einzelne Funktion umstellen und danach messen, ohne
irgendetwas anderes anzufassen.

Was hier ausdrücklich NICHT passiert
------------------------------------
Die Zuordnung ändert sich nicht von selbst. Ein Programm, das eigenständig auf
ein günstigeres Modell umschwenkt, weil die letzten Antworten "gut aussahen",
wäre nicht überprüfbar: schlechtere KI-Antworten sind keine Fehler, die
auffallen -- sie sind nur schlechter. Diese Entscheidung trifft ein Mensch,
auf Grundlage gemessener Zahlen.
"""

from __future__ import annotations

import logging
from typing import Dict

from services import umgebung

logger = logging.getLogger(__name__)

GROSS = "gross"
KLEIN = "klein"
STUFEN = (GROSS, KLEIN)

# ----------------------------------------------------------------------
# Die Tabelle
# ----------------------------------------------------------------------
# Jede Funktion, die Gemini aufruft, steht hier -- auch die, die auf der
# günstigen Stufe laufen. Eine Zeile "klein" ist eine Entscheidung; eine
# fehlende Zeile wäre ein Versehen, und das soll man unterscheiden können.
#
# Der Name links ist derselbe, der als ``feature=`` protokolliert wird und in
# ai_calls.funktion landet. Damit lassen sich Tabelle und Messung direkt
# nebeneinanderlegen.
ZUORDNUNG: Dict[str, str] = {
    # Die Deck-Analyse baut ein umfangreiches JSON nach festem Schema und muss
    # dabei aus echten Kartendaten argumentieren. Sie ist die einzige Funktion,
    # für die bisher die grosse Stufe vorgesehen war.
    "deck_analyse": GROSS,

    # Regelauskunft. Bekommt einen Regelauszug mitgeliefert und muss daraus
    # zitieren, nicht aus dem Gedächtnis antworten.
    "judge": KLEIN,

    # Unterhaltung, keine Auskunft -- hier ist Sprachwitz gefragt, nicht
    # Regelfestigkeit.
    "deck_roast": KLEIN,

    # Kartennamen und -texte übersetzen. Kurze Prompts, und das Ergebnis wird
    # ohnehin gegen Scryfall geprüft (services/multilingual_search.py) --
    # das Modell darf hier gar nichts entscheiden, was nicht nachprüfbar ist.
    "kartenname_uebersetzung": KLEIN,
    "kartenname_auswahl": KLEIN,
    "kartentext_uebersetzung": KLEIN,

    # Nur ein Auffangnetz, wenn die Combo-Datenbank nichts hergibt.
    "combo_fallback": KLEIN,

    # Live-Vision: viele Aufrufe je Sitzung (alle 12,5 s), kurze Antworten.
    # Die teure Stufe wäre hier der grösste Einzelposten überhaupt.
    "vision_erkennung": KLEIN,
    "vision_rat": KLEIN,
    "karte_erkennen": KLEIN,
}

# Womit eine unbekannte Funktion läuft. Bewusst die günstige Stufe: eine neue
# Funktion, die versehentlich ohne Eintrag bleibt, soll kein Geld kosten,
# sondern auffallen (siehe Warnung unten).
STANDARD = KLEIN


def stufe_fuer(funktion: str) -> str:
    """Welche Stufe diese Funktion benutzen soll.

    Reihenfolge: Umgebungsvariable, dann Tabelle, dann Standard.
    """
    name = (funktion or "").strip()

    ueberschrieben = umgebung.text(f"GEMINI_STUFE_{name.upper()}").lower()
    if ueberschrieben:
        if ueberschrieben in STUFEN:
            return ueberschrieben
        logger.error(
            "GEMINI_STUFE_%s=%r ist keine bekannte Stufe (%s) -- der Wert wird "
            "ignoriert.", name.upper(), ueberschrieben, "/".join(STUFEN))

    if name in ZUORDNUNG:
        return ZUORDNUNG[name]

    # Kein Eintrag heisst: hier hat jemand eine Funktion hinzugefügt und die
    # Tabelle nicht ergänzt. Das ist keine Katastrophe (es läuft auf der
    # günstigen Stufe weiter), soll aber im Protokoll stehen.
    logger.warning(
        "Funktion %r steht nicht in services/ki_modelle.ZUORDNUNG -- es gilt "
        "die Stufe %r. Bitte dort eintragen, damit die Modellwahl "
        "nachvollziehbar bleibt.", name, STANDARD)
    return STANDARD


def uebersicht() -> Dict[str, str]:
    """Alle Funktionen mit der Stufe, die gerade wirklich gilt.

    Für werkzeuge/ki_kosten.py und für die Frage "was läuft womit?", ohne
    dafür Quelltext lesen zu müssen.
    """
    return {funktion: stufe_fuer(funktion) for funktion in sorted(ZUORDNUNG)}
