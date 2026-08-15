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
_ADD_BELIEBIG = re.compile(r"\badds?\b\s+\w+\s+mana\s+of\s+any\s+(?:one\s+)?color", re.IGNORECASE)
# Wortgrenze ist hier entscheidend: "add" steckt auch in "additional".
_ADD_WORT = re.compile(r"\badds?\b", re.IGNORECASE)


def farbbedarf(mana_cost: str) -> Dict[Tuple[str, ...], int]:
    """Zerlegt eine Kostenzeile in Farbanforderungen.

    Der Schlüssel ist die GRUPPE von Farben, aus der ein Symbol bezahlt werden
    darf -- nicht die einzelne Farbe:

        {1}{R}{R}       -> {("R",): 2}
        {1}{U/R}{U/R}   -> {("R", "U"): 2}
        {2}{W}{U}       -> {("W",): 1, ("U",): 1}

    Genau hier lag der Fehler: {U/R}{U/R} wurde als "2x Blau UND 2x Rot"
    gezählt. Eclipsed Flamekin ({1}{U/R}{U/R}) galt damit in einem
    blau-roten Deck mit 21 Ländern als nicht bezahlbar, obwohl JEDES dieser
    Länder eines der beiden Symbole bezahlt. Die Karte braucht zwei Mana aus
    dem gemeinsamen Vorrat, nicht zwei je Farbe.

    Nicht als Farbanforderung zählen:
      * {2/R} -- zwei generische Mana tun es auch, die Karte wird nur teurer;
      * {R/P} -- phyrexianisch, notfalls mit zwei Lebenspunkten bezahlbar;
      * {C}, {S}, {X} und Zahlen -- keine Farbe.
    """
    bedarf: Dict[Tuple[str, ...], int] = {}
    for symbol in _SYMBOL.findall(mana_cost or ""):
        teile = [t.strip().upper() for t in symbol.split("/")]
        if any(t == "P" for t in teile):
            continue
        if any(t.isdigit() for t in teile):
            continue
        # In WUBRG-Reihenfolge, wie Magic Farben immer nennt -- alphabetisch
        # käme "Rot/Blau" heraus.
        farben = tuple(sorted({t for t in teile if t in FARBEN}, key=FARBEN.index))
        if not farben:
            continue
        bedarf[farben] = bedarf.get(farben, 0) + 1
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
    #
    # Mit Wortgrenze: "add" steckt auch in "additional". Ohne sie galt jede
    # Karte mit "as an additional cost, pay {1}{R}" oder "Kicker {2}{U}" als
    # Manaquelle -- und tauchte in der Analyse als Quelle einer Farbe auf, die
    # sie nie erzeugt.
    gefunden: set = set()
    for satz in re.split(r"(?<=[.;])\s+|\n", text):
        treffer = _ADD_WORT.search(satz)
        if not treffer:
            continue
        for symbol in _SYMBOL.findall(satz[treffer.end():]):
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

    # Quellen je Gruppe zählen wir NICHT farbweise auf, sondern über die
    # Vereinigung: ein Land, das Blau oder Rot liefert, bezahlt ein {U/R}
    # genau einmal -- doppelt zählen würde die Basis schönrechnen.
    land_farben: List[Tuple[int, set]] = []
    andere_farben: List[Tuple[int, set]] = []

    # Härtester Bedarf je Gruppe: (Symbolzahl, frühester Zug, Kartenname)
    haerteste: Dict[Tuple[str, ...], Tuple[int, int, str]] = {}
    gesamt_symbole: Dict[Tuple[str, ...], int] = {}

    for anzahl, info in karten:
        farben = erzeugte_farben(info)
        if farben:
            (land_farben if _ist_land(info) else andere_farben).append((anzahl, farben))

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

        for gruppe, anzahl_symbole in bedarf.items():
            gesamt_symbole[gruppe] = gesamt_symbole.get(gruppe, 0) + anzahl_symbole * anzahl
            bisher = haerteste.get(gruppe)
            # Härter ist: mehr Symbole; bei gleicher Symbolzahl der frühere Zug.
            if (bisher is None
                    or anzahl_symbole > bisher[0]
                    or (anzahl_symbole == bisher[0] and zug < bisher[1])):
                haerteste[gruppe] = (anzahl_symbole, zug, info.get("name", ""))

    def quellen_fuer(gruppe: Tuple[str, ...], liste: List[Tuple[int, set]]) -> int:
        ziel = set(gruppe)
        return sum(anzahl for anzahl, farben in liste if farben & ziel)

    # Nur Gruppen, die das Deck tatsächlich verlangt. Eine Zeile "Weiss --
    # keine Karte verlangt diese Farbe" ist reines Rauschen.
    ergebnis: List[Dict[str, Any]] = []
    for gruppe in sorted(haerteste, key=lambda g: (len(g), [FARBEN.index(f) for f in g])):
        symbole, zug, kartenname = haerteste[gruppe]
        gesehen = gesehene_karten(zug, auf_dem_spiel)
        quellen = quellen_fuer(gruppe, land_farben)
        p = wahrscheinlichkeit(deckgroesse, quellen, gesehen, symbole)
        noetig = noetige_quellen(deckgroesse, gesehen, symbole)

        ergebnis.append({
            # Schlüssel und Anzeigename für eine Gruppe: ("R", "U") wird zu
            # "U/R" bzw. "Blau/Rot" -- eine Anforderung, kein Farbpaar.
            "schluessel": "/".join(gruppe),
            "farben": list(gruppe),
            "farbe": gruppe[0],
            "farbname": "/".join(FARBNAMEN[f] for f in gruppe),
            "hybrid": len(gruppe) > 1,
            "laender": quellen,
            "weitere_quellen": quellen_fuer(gruppe, andere_farben),
            "symbole_gesamt": gesamt_symbole.get(gruppe, 0),
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
