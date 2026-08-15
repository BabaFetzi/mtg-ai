"""services/manabasis.py -- Farbquellen eines Decks prüfen.

Die häufigste Ursache dafür, dass ein sauber gebautes Deck trotzdem verliert:
zu wenige Länder einer Farbe. Eine Karte mit {R}{R} auf Zug 2 braucht deutlich
mehr rote Quellen als eine mit einem einzelnen {R} auf Zug 4 -- das sieht man
einer Deckliste nicht an.

Diese Prüfung rechnet die Wahrscheinlichkeit direkt aus, statt sie aus einer
Tabelle abzuschreiben: hypergeometrische Verteilung über die bis zum
betreffenden Zug gesehenen Karten. Damit steht hinter jeder Zahl eine
nachvollziehbare Rechnung und keine Faustregel.
"""

from __future__ import annotations

import re
from math import comb
from typing import Any, Dict, Iterable, List, Tuple

FARBEN = ("W", "U", "B", "R", "G")

FARBNAMEN = {
    "W": "Weiss",
    "U": "Blau",
    "B": "Schwarz",
    "R": "Rot",
    "G": "Grün",
}

# Ab dieser Wahrscheinlichkeit gilt eine Farbe als verlässlich verfügbar.
ZIEL_WAHRSCHEINLICHKEIT = 0.90

# Später als Zug 6 rechnen wir nicht -- danach hat man so viele Karten gesehen,
# dass die Rechnung nichts mehr aussagt.
MAX_ZUG = 6

_SYMBOL = re.compile(r"\{([^}]+)\}")
_ADD_BELIEBIG = re.compile(r"add\s+\w+\s+mana\s+of\s+any\s+(?:one\s+)?color", re.IGNORECASE)


def farbbedarf(mana_cost: str) -> Dict[str, int]:
    """Zählt farbige Manasymbole einer Kostenzeile.

    Hybride Symbole ({R/G}, {2/R}) zählen für JEDE beteiligte Farbe, weil sie
    sich mit jeder davon bezahlen lassen -- der Bedarf an einer einzelnen Farbe
    steigt dadurch nicht. Phyrexianische Symbole ({R/P}) zählen aus demselben
    Grund mit, sind aber notfalls über Lebenspunkte bezahlbar.
    """
    bedarf: Dict[str, int] = {}
    for symbol in _SYMBOL.findall(mana_cost or ""):
        teile = [t.strip().upper() for t in symbol.split("/")]
        farben = {t for t in teile if t in FARBEN}
        for f in farben:
            bedarf[f] = bedarf.get(f, 0) + 1
    return bedarf


def erzeugte_farben(info: Dict[str, Any]) -> set:
    """Welche Farben erzeugt diese Karte?

    Bevorzugt das Feld produced_mana aus den Kartendaten. Ältere Einträge aus
    dem Cache haben es noch nicht -- dann wird der Regeltext gelesen, damit die
    Analyse nicht stillschweigend zu wenige Quellen zählt.
    """
    erzeugt = info.get("produced_mana")
    if erzeugt:
        return {f for f in (str(x).upper() for x in erzeugt) if f in FARBEN}
    if erzeugt == []:
        # Ausdrücklich leer: die Karte erzeugt nachweislich kein Mana.
        return set()

    text = info.get("oracle_text") or ""
    if _ADD_BELIEBIG.search(text):
        return set(FARBEN)

    # Satzweise auswerten: "{T}: Add {U} or {R}." nennt beide Farben, sie
    # stehen aber durch das "or" nicht direkt hintereinander. Deshalb zählen
    # alle Farbsymbole des Satzes, in dem "Add" vorkommt -- nicht die des
    # ganzen Regeltextes, sonst würde "{1}{R}: ..." einer Fähigkeit
    # mitgezählt.
    gefunden: set = set()
    for satz in re.split(r"(?<=[.;])\s+|\n", text):
        if "add" not in satz.lower():
            continue
        _, _, nach_add = satz.lower().partition("add")
        versatz = len(satz) - len(nach_add)
        for symbol in _SYMBOL.findall(satz[versatz:]):
            for teil in symbol.split("/"):
                teil = teil.strip().upper()
                if teil in FARBEN:
                    gefunden.add(teil)
    return gefunden


def _ist_land(info: Dict[str, Any]) -> bool:
    return "land" in (info.get("type") or "").lower()


def wahrscheinlichkeit(deckgroesse: int, quellen: int, gesehen: int, benoetigt: int) -> float:
    """P(mindestens `benoetigt` Quellen unter `gesehen` Karten).

    Hypergeometrisch: aus `deckgroesse` Karten mit `quellen` Treffern werden
    `gesehen` Karten ohne Zurücklegen gezogen.
    """
    if benoetigt <= 0:
        return 1.0
    if quellen < benoetigt or deckgroesse <= 0:
        return 0.0
    gesehen = min(gesehen, deckgroesse)
    gesamt = comb(deckgroesse, gesehen)
    if gesamt == 0:
        return 0.0
    treffer = 0
    for k in range(benoetigt, min(quellen, gesehen) + 1):
        treffer += comb(quellen, k) * comb(deckgroesse - quellen, gesehen - k)
    return treffer / gesamt


def noetige_quellen(deckgroesse: int, gesehen: int, benoetigt: int,
                    ziel: float = ZIEL_WAHRSCHEINLICHKEIT) -> int:
    """Kleinste Quellenzahl, die das Ziel erreicht (0, wenn unerreichbar)."""
    for s in range(benoetigt, deckgroesse + 1):
        if wahrscheinlichkeit(deckgroesse, s, gesehen, benoetigt) >= ziel:
            return s
    return 0


def gesehene_karten(zug: int, auf_dem_spiel: bool = True) -> int:
    """Karten, die man bis einschliesslich `zug` gesehen hat.

    Auf dem Spiel (ohne den Zug-1-Zug): 7 + (zug - 1). Bewusst die
    ungünstigere Annahme -- wer anfängt, zieht eine Karte weniger.
    """
    return 7 + max(0, zug - 1) + (0 if auf_dem_spiel else 1)


def analysiere(karten: Iterable[Tuple[int, Dict[str, Any]]],
               auf_dem_spiel: bool = True) -> Dict[str, Any]:
    """Farbquellen gegen Farbbedarf.

    `karten` ist eine Folge aus (Anzahl, Kartendaten) des Hauptdecks.
    """
    karten = [(int(a), i) for a, i in karten if i]
    deckgroesse = sum(a for a, _ in karten)

    laender: Dict[str, int] = {f: 0 for f in FARBEN}
    andere_quellen: Dict[str, int] = {f: 0 for f in FARBEN}
    # Härtester Bedarf je Farbe: (Symbolzahl, frühester Zug, Kartenname)
    haerteste: Dict[str, Tuple[int, int, str]] = {}
    gesamt_symbole: Dict[str, int] = {f: 0 for f in FARBEN}

    for anzahl, info in karten:
        farben = erzeugte_farben(info)
        if farben:
            ziel = laender if _ist_land(info) else andere_quellen
            for f in farben:
                ziel[f] += anzahl

        if _ist_land(info):
            continue

        bedarf = farbbedarf(info.get("mana_cost") or "")
        if not bedarf:
            continue
        try:
            zug = int(float(info.get("cmc") or 0))
        except (TypeError, ValueError):
            zug = 0
        zug = max(1, min(zug or 1, MAX_ZUG))

        for f, anzahl_symbole in bedarf.items():
            gesamt_symbole[f] += anzahl_symbole * anzahl
            bisher = haerteste.get(f)
            # Härter ist: mehr Symbole; bei gleicher Symbolzahl der frühere Zug.
            if (bisher is None
                    or anzahl_symbole > bisher[0]
                    or (anzahl_symbole == bisher[0] and zug < bisher[1])):
                haerteste[f] = (anzahl_symbole, zug, info.get("name", ""))

    ergebnis: List[Dict[str, Any]] = []
    for f in FARBEN:
        if not haerteste.get(f) and not laender[f] and not andere_quellen[f]:
            continue
        symbole, zug, kartenname = haerteste.get(f, (0, 1, ""))
        gesehen = gesehene_karten(zug, auf_dem_spiel)
        quellen = laender[f]
        p = wahrscheinlichkeit(deckgroesse, quellen, gesehen, symbole) if symbole else 1.0
        noetig = noetige_quellen(deckgroesse, gesehen, symbole) if symbole else 0

        ergebnis.append({
            "farbe": f,
            "farbname": FARBNAMEN[f],
            "laender": quellen,
            "weitere_quellen": andere_quellen[f],
            "symbole_gesamt": gesamt_symbole[f],
            "haertester_bedarf": symbole,
            "haerteste_karte": kartenname,
            "zug": zug,
            "wahrscheinlichkeit": round(p, 3),
            "empfohlene_laender": noetig,
            "fehlende_laender": max(0, noetig - quellen),
            "reicht": bool(symbole == 0 or p >= ZIEL_WAHRSCHEINLICHKEIT),
        })

    landkarten = sum(a for a, i in karten if _ist_land(i))
    return {
        "deckgroesse": deckgroesse,
        "laender_gesamt": landkarten,
        "auf_dem_spiel": auf_dem_spiel,
        "ziel": ZIEL_WAHRSCHEINLICHKEIT,
        "farben": ergebnis,
    }
