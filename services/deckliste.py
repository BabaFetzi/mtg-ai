"""services/deckliste.py -- Zeilen einer Deckliste ändern.

Hinzufügen, Entfernen und Auflage-Wechseln arbeiten alle auf demselben Text.
Stünden sie in drei Endpunkten nebeneinander, würden sie auseinanderlaufen: der
eine erkennt eine Zeile, die der andere übersieht, und der Nutzer sieht ein Deck,
das je nach Knopf anders aussieht. Deshalb steht die Zeilenlogik genau einmal
hier -- und lässt sich ohne HTTP und ohne Datenbank prüfen.

Zwei Zusagen an den Nutzer, die dieses Modul einhält:

1. **Struktur bleibt.** Leerzeilen, Kommentare und Überschriften wie "Sideboard"
   werden nie umgeschrieben. Wer seine Liste ordentlich gegliedert hat, findet
   sie nach einem Klick unverändert gegliedert vor.
2. **Die Auflage ist Teil der Identität.** "Lightning Bolt (2XM) 123" und
   "Lightning Bolt (M10) 146" sind zwei Zeilen, nicht eine. Genau darum geht es
   bei "welche Version habe ich": Wer zwei verschiedene Drucke besitzt, soll
   beide im Deck führen können.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from services.auflagen import auflage_anhaengen, auflage_lesen, gleiche_auflage
from services.scryfall import clean_card_name

# Dieselben Überschriften, die parse_decklist überspringt. Liefen die beiden
# Listen auseinander, würde eine Zeile hier als Karte und dort als Überschrift
# gelten -- und der Nutzer bekäme "2x Sideboard" ins Deck geschrieben.
_UEBERSCHRIFTEN = {"deck", "commander", "companion", "sideboard", "mainboard", "main"}

_MIT_ANZAHL = re.compile(r'^(\d+)[xX]?\s+(.+)$')


def ist_strukturzeile(zeile: str) -> bool:
    """Leerzeile, Kommentar oder Überschrift -- also keine Karte."""
    text = (zeile or "").strip()
    if not text:
        return True
    if text.startswith('#') or text.startswith('//'):
        return True
    if text.endswith(':'):
        return True
    return text.lower() in _UEBERSCHRIFTEN


def zeile_lesen(zeile: str) -> Optional[Dict[str, Any]]:
    """Eine Kartenzeile in ihre Bestandteile -- oder None bei Struktur.

    'roh_name' ist der Name so, wie er in der Liste steht (ohne Auflage, aber
    ungereinigt); 'name' ist die Vergleichsform. Beim Zurückschreiben wird
    'roh_name' benutzt: die Schreibweise des Nutzers bleibt erhalten.
    """
    if ist_strukturzeile(zeile):
        return None
    text = zeile.strip()
    treffer = _MIT_ANZAHL.match(text)
    rest = treffer.group(2).strip() if treffer else text
    roh_name, set_code, nummer = auflage_lesen(rest)
    return {
        "anzahl": int(treffer.group(1)) if treffer else 1,
        "hatte_anzahl": bool(treffer),
        "roh_name": roh_name,
        "name": clean_card_name(roh_name).lower(),
        "set": set_code,
        "sammlernummer": nummer,
    }


def zeile_schreiben(eintrag: Dict[str, Any]) -> str:
    """Baut aus den Bestandteilen wieder eine Zeile."""
    name = auflage_anhaengen(eintrag["roh_name"], eintrag.get("set"),
                             eintrag.get("sammlernummer"))
    return f"{eintrag['anzahl']}x {name}"


def _passt(eintrag: Dict[str, Any], name: str,
           set_code: Optional[str], nummer: Optional[str],
           auch_ohne_auflage: bool) -> bool:
    if eintrag["name"] != clean_card_name(name).lower():
        return False
    if auch_ohne_auflage:
        return True
    return gleiche_auflage(eintrag.get("set"), eintrag.get("sammlernummer"), set_code, nummer)


def _finde(zeilen: List[str], name: str, set_code: Optional[str],
           nummer: Optional[str]) -> Optional[int]:
    """Index der Zeile, die gemeint ist -- oder None.

    Zuerst wird die Zeile mit GENAU dieser Auflage gesucht. Nur wenn keine
    Auflage angegeben wurde, gilt ersatzweise die erste Zeile mit demselben
    Namen: Wer aus der Kartensuche ein schlichtes "Lightning Bolt" hinzufügt,
    erwartet, dass sein vorhandener Bolt hochgezählt wird, egal aus welchem Set.

    Umgekehrt gilt das NICHT. Wer ausdrücklich "(2XM) 123" wählt, meint diese
    Auflage -- und bekommt eine neue Zeile, statt dass eine andere Auflage
    stillschweigend hochgezählt wird.
    """
    gelesen = [(i, zeile_lesen(z)) for i, z in enumerate(zeilen)]
    for i, eintrag in gelesen:
        if eintrag and _passt(eintrag, name, set_code, nummer, auch_ohne_auflage=False):
            return i
    if set_code:
        return None
    for i, eintrag in gelesen:
        if eintrag and _passt(eintrag, name, set_code, nummer, auch_ohne_auflage=True):
            return i
    return None


def karte_hinzufuegen(liste: str, name: str, set_code: Optional[str] = None,
                      sammlernummer: Optional[str] = None) -> str:
    """Ein Exemplar mehr. Neue Karte -> neue Zeile am Ende."""
    zeilen = (liste or "").split('\n')
    index = _finde(zeilen, name, set_code, sammlernummer)

    if index is None:
        neu = auflage_anhaengen(name.strip(), set_code, sammlernummer)
        # Nachlaufende Leerzeilen abschneiden, damit die neue Karte direkt unter
        # der letzten steht und nicht hinter einer wachsenden Lücke.
        while zeilen and not zeilen[-1].strip():
            zeilen.pop()
        zeilen.append(f"1x {neu}")
        return '\n'.join(zeilen)

    eintrag = zeile_lesen(zeilen[index])
    eintrag["anzahl"] += 1
    zeilen[index] = zeile_schreiben(eintrag)
    return '\n'.join(zeilen)


def karte_entfernen(liste: str, name: str, set_code: Optional[str] = None,
                    sammlernummer: Optional[str] = None) -> Tuple[str, bool]:
    """Ein Exemplar weniger. Bei 0 verschwindet die Zeile.

    Returns:
        (neue_liste, gefunden). `gefunden=False` heisst: die Karte stand gar
        nicht im Deck -- der Aufrufer soll das sagen, nicht so tun, als hätte
        er etwas entfernt.
    """
    zeilen = (liste or "").split('\n')
    index = _finde(zeilen, name, set_code, sammlernummer)
    if index is None:
        return (liste or ""), False

    eintrag = zeile_lesen(zeilen[index])
    eintrag["anzahl"] -= 1
    if eintrag["anzahl"] > 0:
        zeilen[index] = zeile_schreiben(eintrag)
    else:
        zeilen.pop(index)
    return '\n'.join(zeilen), True


def auflage_setzen(liste: str, name: str,
                   alt_set: Optional[str], alt_nummer: Optional[str],
                   neu_set: Optional[str], neu_nummer: Optional[str]) -> Tuple[str, bool]:
    """Wechselt die Auflage einer Karte im Deck.

    Steht dieselbe Karte danach zweimal in derselben Auflage, werden die beiden
    Zeilen zusammengefasst. Zwei Zeilen mit identischer Auflage wären keine
    Information, sondern ein Fehler im Deck -- und beim nächsten Bearbeiten
    würde nur eine davon gefunden.

    Returns:
        (neue_liste, gefunden).
    """
    zeilen = (liste or "").split('\n')
    index = _finde(zeilen, name, alt_set, alt_nummer)
    if index is None:
        return (liste or ""), False

    eintrag = zeile_lesen(zeilen[index])
    eintrag["set"] = (neu_set or "").strip().lower() or None
    eintrag["sammlernummer"] = (neu_nummer or "").strip() or None

    # Gibt es die Zielauflage schon als eigene Zeile? Dann zusammenlegen.
    for i, zeile in enumerate(zeilen):
        if i == index:
            continue
        anderer = zeile_lesen(zeile)
        if not anderer or anderer["name"] != eintrag["name"]:
            continue
        if gleiche_auflage(anderer.get("set"), anderer.get("sammlernummer"),
                           eintrag.get("set"), eintrag.get("sammlernummer")):
            anderer["anzahl"] += eintrag["anzahl"]
            zeilen[i] = zeile_schreiben(anderer)
            zeilen.pop(index)
            return '\n'.join(zeilen), True

    zeilen[index] = zeile_schreiben(eintrag)
    return '\n'.join(zeilen), True
