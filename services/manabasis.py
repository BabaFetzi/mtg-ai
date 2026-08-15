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
from functools import lru_cache
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


# ----------------------------------------------------------------------
# Mit Mulligan
# ----------------------------------------------------------------------
# Niemand behält eine Hand mit einem Land. Ohne diesen Schritt fällt die
# Rechnung strenger aus als die Wirklichkeit -- sie empfiehlt Quellen, die
# ein Deck gar nicht unterbringen kann.
#
# Angenommene Regel, bewusst einfach und benennbar:
#   * Eine Starthand mit weniger als 2 oder mehr als 5 Ländern wird geworfen.
#   * Es wird höchstens einmal gemulligant (London: sieben ziehen, eine
#     zurücklegen -- zurückgelegt wird eine Karte, die keine Quelle ist).
#   * Danach wird die Hand behalten, egal wie sie aussieht.
# Alles darüber hinaus (zweiter Mulligan, Kartenauswahl beim Zurücklegen)
# bliebe Geschmackssache und würde die Zahl nur scheingenau machen.
MIN_LAENDER_KEEP = 2
MAX_LAENDER_KEEP = 5
STARTHAND = 7


def _mehrfach_hyper(gesamt: int, gruppen: Tuple[int, ...], gezogen: Tuple[int, ...]) -> float:
    """Wahrscheinlichkeit einer bestimmten Zusammensetzung beim Ziehen."""
    rest_gruppe = gesamt - sum(gruppen)
    rest_gezogen = sum(gezogen)
    if rest_gruppe < 0:
        return 0.0
    zaehler = 1
    for groesse, wieviel in zip(gruppen, gezogen):
        if wieviel > groesse:
            return 0.0
        zaehler *= comb(groesse, wieviel)
    uebrig = STARTHAND - rest_gezogen
    if uebrig < 0 or uebrig > rest_gruppe:
        return 0.0
    zaehler *= comb(rest_gruppe, uebrig)
    nenner = comb(gesamt, STARTHAND)
    return zaehler / nenner if nenner else 0.0


@lru_cache(maxsize=4096)
def wahrscheinlichkeit_mit_mulligan(deckgroesse: int, quellen: int, laender: int,
                                    zusatzkarten: int, benoetigt: int) -> float:
    """P(genug Quellen), wenn schlechte Starthände geworfen werden.

    `zusatzkarten` sind die nach der Starthand gezogenen Karten (auf dem Spiel
    also Zug minus eins). `laender` ist die Gesamtzahl der Länder im Deck; sie
    entscheidet, ob eine Hand behalten wird. `quellen` sind die Länder, die die
    gesuchte Farbe liefern -- sie sind eine Teilmenge davon.
    """
    if benoetigt <= 0:
        return 1.0
    if deckgroesse <= 0 or quellen < benoetigt:
        return 0.0
    quellen = min(quellen, laender, deckgroesse)
    laender = min(laender, deckgroesse)
    andere_laender = laender - quellen

    # Hand nach einem Mulligan: sieben ziehen, eine Nicht-Quelle zurücklegen.
    # Wer sieben Quellen zieht, muss eine davon zurücklegen.
    nach_mulligan = 0.0
    for s in range(0, min(quellen, STARTHAND) + 1):
        p = wahrscheinlichkeit_genau(deckgroesse, quellen, STARTHAND, s)
        if p <= 0:
            continue
        behalten = min(s, STARTHAND - 1)
        nach_mulligan += p * wahrscheinlichkeit(
            deckgroesse - STARTHAND, quellen - s, zusatzkarten, benoetigt - behalten)

    gesamt = 0.0
    for s in range(0, min(quellen, STARTHAND) + 1):
        for l in range(0, min(andere_laender, STARTHAND - s) + 1):
            p = _mehrfach_hyper(deckgroesse, (quellen, andere_laender), (s, l))
            if p <= 0:
                continue
            if MIN_LAENDER_KEEP <= s + l <= MAX_LAENDER_KEEP:
                gesamt += p * wahrscheinlichkeit(
                    deckgroesse - STARTHAND, quellen - s, zusatzkarten, benoetigt - s)
            else:
                gesamt += p * nach_mulligan
    return gesamt


def wahrscheinlichkeit_genau(deckgroesse: int, quellen: int, gezogen: int, treffer: int) -> float:
    """P(GENAU `treffer` Quellen unter `gezogen` Karten)."""
    if treffer > quellen or treffer > gezogen or deckgroesse <= 0:
        return 0.0
    nenner = comb(deckgroesse, gezogen)
    if nenner == 0:
        return 0.0
    rest = deckgroesse - quellen
    if gezogen - treffer > rest:
        return 0.0
    return comb(quellen, treffer) * comb(rest, gezogen - treffer) / nenner


def noetige_quellen_mit_mulligan(deckgroesse: int, laender: int, zusatzkarten: int,
                                 benoetigt: int, ziel: float = ZIEL_WAHRSCHEINLICHKEIT) -> int:
    """Kleinste Quellenzahl, die das Ziel erreicht (0, wenn unerreichbar).

    Mehr Quellen können nie schaden, die Wahrscheinlichkeit steigt monoton --
    deshalb reicht das erste Erreichen.
    """
    for s in range(benoetigt, min(laender, deckgroesse) + 1):
        if wahrscheinlichkeit_mit_mulligan(deckgroesse, s, laender, zusatzkarten, benoetigt) >= ziel:
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
    # Manasteine und Manakreaturen: mit ihren Kosten, denn sie stehen erst ab
    # dem Zug danach zur Verfügung.
    andere_farben: List[Tuple[int, set, int]] = []

    # Härtester Bedarf je Gruppe: (Symbolzahl, frühester Zug, Kartenname)
    haerteste: Dict[Tuple[str, ...], Tuple[int, int, str]] = {}
    gesamt_symbole: Dict[Tuple[str, ...], int] = {}

    def kosten_von(info: Dict[str, Any]) -> int:
        try:
            return int(float(info.get("cmc") or 0))
        except (TypeError, ValueError):
            return 0

    for anzahl, info in karten:
        farben = erzeugte_farben(info)
        if farben:
            if _ist_land(info):
                land_farben.append((anzahl, farben))
            else:
                andere_farben.append((anzahl, farben, kosten_von(info)))

        if _ist_land(info):
            continue

        bedarf = farbbedarf(info.get("mana_cost") or "")
        if not bedarf:
            continue
        zug = max(1, min(kosten_von(info) or 1, MAX_ZUG))

        for gruppe, anzahl_symbole in bedarf.items():
            gesamt_symbole[gruppe] = gesamt_symbole.get(gruppe, 0) + anzahl_symbole * anzahl
            bisher = haerteste.get(gruppe)
            # Härter ist: mehr Symbole; bei gleicher Symbolzahl der frühere Zug.
            if (bisher is None
                    or anzahl_symbole > bisher[0]
                    or (anzahl_symbole == bisher[0] and zug < bisher[1])):
                haerteste[gruppe] = (anzahl_symbole, zug, info.get("name", ""))

    def laender_fuer(gruppe: Tuple[str, ...]) -> int:
        ziel = set(gruppe)
        return sum(anzahl for anzahl, farben in land_farben if farben & ziel)

    def andere_fuer(gruppe: Tuple[str, ...], bis_zug: int = MAX_ZUG + 1) -> int:
        """Manasteine und Manakreaturen der Gruppe.

        `bis_zug` grenzt auf die ein, die bis dahin überhaupt im Spiel sein
        können: ein Stein für drei Mana hilft einer Karte auf Zug 3 nicht, er
        wird frühestens in diesem Zug selbst gespielt.
        """
        ziel = set(gruppe)
        return sum(anzahl for anzahl, farben, kosten in andere_farben
                   if farben & ziel and kosten < bis_zug)

    landkarten = sum(a for a, i in karten if _ist_land(i))

    # Nur Gruppen, die das Deck tatsächlich verlangt. Eine Zeile "Weiss --
    # keine Karte verlangt diese Farbe" ist reines Rauschen.
    ergebnis: List[Dict[str, Any]] = []
    for gruppe in sorted(haerteste, key=lambda g: (len(g), [FARBEN.index(f) for f in g])):
        symbole, zug, kartenname = haerteste[gruppe]
        # Auf dem Spiel: Starthand plus (Zug - 1) gezogene Karten.
        zusatzkarten = max(0, zug - 1) + (0 if auf_dem_spiel else 1)
        laender_der_gruppe = laender_fuer(gruppe)
        # Rechtzeitige Manasteine zählen mit -- sie ganz auszunehmen stellt ein
        # Deck mit acht solcher Quellen zu schlecht dar.
        rechtzeitige_andere = andere_fuer(gruppe, bis_zug=zug)
        quellen = laender_der_gruppe + rechtzeitige_andere

        p = wahrscheinlichkeit_mit_mulligan(
            deckgroesse, quellen, landkarten + rechtzeitige_andere, zusatzkarten, symbole)
        noetig = noetige_quellen_mit_mulligan(
            deckgroesse, landkarten + rechtzeitige_andere, zusatzkarten, symbole)

        ergebnis.append({
            # Schlüssel und Anzeigename für eine Gruppe: ("R", "U") wird zu
            # "U/R" bzw. "Blau/Rot" -- eine Anforderung, kein Farbpaar.
            "schluessel": "/".join(gruppe),
            "farben": list(gruppe),
            "farbe": gruppe[0],
            "farbname": "/".join(FARBNAMEN[f] for f in gruppe),
            "hybrid": len(gruppe) > 1,
            "laender": laender_der_gruppe,
            "quellen": quellen,
            "weitere_quellen": andere_fuer(gruppe),
            "weitere_quellen_rechtzeitig": rechtzeitige_andere,
            "symbole_gesamt": gesamt_symbole.get(gruppe, 0),
            "haertester_bedarf": symbole,
            "haerteste_karte": kartenname,
            "zug": zug,
            "wahrscheinlichkeit": round(p, 3),
            # noetig == 0 heisst: auch wenn JEDES Land der Gruppe zählen
            # würde, wird das Ziel nicht erreicht. Dann hilft keine
            # Umverteilung, sondern nur mehr Länder oder eine weniger
            # farbintensive Karte.
            "empfohlene_laender": noetig,
            "erreichbar": noetig > 0,
            "fehlende_laender": max(0, noetig - quellen) if noetig else 0,
            "reicht": bool(symbole == 0 or p >= ZIEL_WAHRSCHEINLICHKEIT),
        })

    return {
        "deckgroesse": deckgroesse,
        "laender_gesamt": landkarten,
        "auf_dem_spiel": auf_dem_spiel,
        "ziel": ZIEL_WAHRSCHEINLICHKEIT,
        "farben": ergebnis,
    }
