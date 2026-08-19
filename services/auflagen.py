"""services/auflagen.py -- Welche Auflage einer Karte steht im Deck?

Eine Karte wie Lightning Bolt gibt es in über vierzig Auflagen. Welche davon
jemand besitzt und ins Deck legt, entscheidet über Bild und Preis -- eine Alpha-
Auflage kostet das Tausendfache des Nachdrucks. Bisher warf die Deckliste diese
Angabe weg: `clean_card_name` entfernte "(2XM) 123" ersatzlos.

Gespeichert wird die Auflage dort, wo sie hingehört: in der Deckliste selbst, im
Format, das Moxfield, Arena und MTGO ohnehin schreiben::

    4x Lightning Bolt (2XM) 123

Kein zweiter Speicherort, keine Schemaänderung -- und eine Deckliste, die man
weiterhin bei jedem anderen Werkzeug einfügen kann.

Wichtig: die Auflage steuert **nur Bild und Preis**. Für den Abgleich mit der
Sammlung zählt jede Auflage einer Karte als dieselbe Karte -- wer einen Bolt aus
2XM besitzt, dem fehlt kein Bolt, bloss weil im Deck der aus M10 steht.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# Foil-Kennzeichnungen stehen hinter der Auflage ("... (2XM) 123 *F*") und
# müssten sonst als Sammlernummer durchgehen.
_FOIL_ENDE = re.compile(r'(?:\*[fF](?:oil)?\*|\bfoil\b)\s*$', re.IGNORECASE)

# Set-Code in runden oder eckigen Klammern, optional gefolgt von der
# Sammlernummer -- und zwar am ZEILENENDE.
#
# Die Begrenzung auf 3-6 Zeichen ist das, was einen Set-Code von einer
# gewöhnlichen Klammerbemerkung trennt: "(2XM)" und "(PLIST)" sind Set-Codes,
# "(Commander)" oder "(Showcase)" sind keine und bleiben unangetastet.
# Sammlernummern dürfen Buchstaben und das Sternchen der Sonderdrucke
# enthalten ("123a", "★42", "T1").
_AUFLAGE = re.compile(
    r'\s*[\(\[](?P<set>[A-Za-z0-9]{3,6})[\)\]]'
    r'(?:\s+(?P<nummer>[A-Za-z0-9★*-]{1,12}))?'
    r'\s*$'
)


def auflage_lesen(rest: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Trennt die Auflage vom Kartennamen.

    Args:
        rest: Der Teil der Deckzeile hinter der Stückzahl,
            z.B. ``"Lightning Bolt (2XM) 123"``.

    Returns:
        (name, set_code, sammlernummer). set_code ist kleingeschrieben --
        Scryfall führt Set-Codes so. Ohne erkennbare Auflage stehen dort
        ``None``; der Name kommt dann unverändert zurück.

    Bewusst konservativ: Was nicht sicher als Auflage erkennbar ist, bleibt Teil
    des Namens und wird von `clean_card_name` wie bisher behandelt. Lieber keine
    Auflage als eine falsche -- eine falsche Auflage zeigt ein falsches Bild und
    einen falschen Preis, und beides sähe aus wie eine Tatsache.
    """
    text = (rest or "").strip()
    if not text:
        return text, None, None

    # Foil-Marke am Ende zwischenlagern, damit die Auflage davor sichtbar wird.
    foil_marke = ""
    treffer_foil = _FOIL_ENDE.search(text)
    if treffer_foil:
        foil_marke = text[treffer_foil.start():]
        text = text[:treffer_foil.start()].rstrip()

    treffer = _AUFLAGE.search(text)
    if not treffer:
        return (text + (" " + foil_marke.strip() if foil_marke else "")).strip(), None, None

    name = text[:treffer.start()].strip()
    if not name:
        # "(2XM) 123" ganz ohne Namen ist keine Kartenzeile -- unverändert lassen.
        return (text + (" " + foil_marke.strip() if foil_marke else "")).strip(), None, None

    nummer = treffer.group("nummer")
    return (
        (name + (" " + foil_marke.strip() if foil_marke else "")).strip(),
        treffer.group("set").lower(),
        nummer.strip() if nummer else None,
    )


def auflage_anhaengen(name: str, set_code: Optional[str],
                      sammlernummer: Optional[str] = None) -> str:
    """Schreibt die Auflage in der Standardschreibweise hinter den Namen.

    Ohne Set-Code kommt der Name unverändert zurück -- eine Sammlernummer allein
    bezeichnet keine Auflage.
    """
    name = (name or "").strip()
    set_code = (set_code or "").strip()
    if not set_code:
        return name
    zeile = f"{name} ({set_code.upper()})"
    nummer = (sammlernummer or "").strip()
    if nummer:
        zeile = f"{zeile} {nummer}"
    return zeile


def gleiche_auflage(a_set: Optional[str], a_nummer: Optional[str],
                    b_set: Optional[str], b_nummer: Optional[str]) -> bool:
    """Bezeichnen beide Angaben dieselbe Auflage?

    Set-Codes werden ohne Rücksicht auf Gross-/Kleinschreibung verglichen. Fehlt
    auf einer Seite die Sammlernummer, entscheidet der Set-Code allein -- eine
    Zeile "4x Lightning Bolt (2XM)" meint dieselbe Auflage wie "(2XM) 123",
    solange nichts Genaueres dasteht.
    """
    a_s = (a_set or "").strip().lower()
    b_s = (b_set or "").strip().lower()
    if a_s != b_s:
        return False
    a_n = (a_nummer or "").strip().lower()
    b_n = (b_nummer or "").strip().lower()
    if not a_n or not b_n:
        return True
    return a_n == b_n


def auflage_schluessel(set_code: Optional[str],
                       sammlernummer: Optional[str]) -> Optional[str]:
    """Vergleichsschlüssel "set/nummer" -- oder None ohne Set-Code."""
    s = (set_code or "").strip().lower()
    if not s:
        return None
    n = (sammlernummer or "").strip().lower()
    return f"{s}/{n}" if n else s


def besitz_schluessel(zeilen) -> Dict[str, int]:
    """Wie viele Exemplare je Auflage liegen in der Sammlung?

    Erwartet Zeilen mit `edition` und `sammlernummer` (so heissen die Spalten in
    `sammlung_alben`) und einer Stückzahl unter `anzahl`. Gezählt wird unter
    beiden Schlüsseln -- "2xm" und "2xm/123" -- damit auch Sammlungseinträge
    ohne erfasste Sammlernummer eine Auflage markieren können.
    """
    besitz: Dict[str, int] = {}
    for zeile in zeilen or []:
        edition = (zeile.get("edition") or "").strip().lower()
        if not edition:
            continue
        try:
            menge = int(zeile.get("anzahl") or 1)
        except (TypeError, ValueError):
            menge = 1
        nummer = (zeile.get("sammlernummer") or "").strip().lower()
        besitz[edition] = besitz.get(edition, 0) + menge
        if nummer:
            genau = f"{edition}/{nummer}"
            besitz[genau] = besitz.get(genau, 0) + menge
    return besitz


def besitz_zu_auflage(besitz: Dict[str, int], set_code: Optional[str],
                      sammlernummer: Optional[str]) -> int:
    """Stückzahl einer bestimmten Auflage aus dem Ergebnis von `besitz_schluessel`.

    Die genaue Sammlernummer hat Vorrang; ist sie in der Sammlung nicht erfasst,
    zählt der Set-Code. Rückgabe 0 heisst "nicht in der Sammlung".
    """
    s = (set_code or "").strip().lower()
    if not s:
        return 0
    n = (sammlernummer or "").strip().lower()
    if n:
        genau = besitz.get(f"{s}/{n}")
        if genau:
            return genau
        # Wer die Auflage ohne Sammlernummer erfasst hat, besitzt sie trotzdem.
        ungenau = besitz.get(s, 0)
        return ungenau if ungenau else 0
    return besitz.get(s, 0)


def zeile_zerlegen(zeile: str) -> Optional[Dict[str, Any]]:
    """Zerlegt eine Deckzeile in Stückzahl, Namensteil und Auflage.

    Gibt None zurück, wenn die Zeile keine Stückzahl trägt -- dann gilt sie
    überall im Programm als einzelnes Exemplar.
    """
    treffer = re.match(r'^(\d+)[xX]?\s+(.+)$', (zeile or "").strip())
    if not treffer:
        return None
    name, set_code, nummer = auflage_lesen(treffer.group(2))
    return {
        "anzahl": int(treffer.group(1)),
        "name": name,
        "set": set_code,
        "sammlernummer": nummer,
    }
