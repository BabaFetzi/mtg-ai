"""
services/synergies.py – Regelbasierte Synergie-Erkennung (offline, ohne KI)

Ergänzt den Combo-Scanner: Wo Commander Spellbook nur *definierte* Combos
(oft unendlich/spielentscheidend) kennt, erkennt dieses Modul *Synergie-Themen*
zwischen Karten -- also Gruppen von Karten, die sich mechanisch gegenseitig
verstärken (z.B. Token-Engine, Aristocrats/Lebensverlust, +1/+1-Counter).

Arbeitet rein auf den Oracle-Texten (Regeltexten) der Karten -- kein API-Key,
keine Kosten, deterministisch. Um Rauschen zu vermeiden, nutzen die meisten
Themen ein Enabler/Payoff-Modell: eine Synergie wird nur gemeldet, wenn sowohl
ein "Auslöser" als auch ein "Nutznießer" (auf verschiedenen Karten) vorhanden
ist.
"""

import re
from typing import List, Dict, Any

# ----------------------------------------------------------------------------
# Themen-Definitionen
#   payoff  : Regex für die "Belohnungs"-Karte (Pflicht)
#   enabler : Regex für die "Auslöser"-Karte (optional). Ist er gesetzt, muss
#             mindestens eine Enabler- UND eine Payoff-Karte vorhanden sein.
#   min     : Mindestanzahl beteiligter (verschiedener) Karten.
# Alle Regexe laufen case-insensitive auf dem englischen Oracle-Text.
# ----------------------------------------------------------------------------
THEMES: List[Dict[str, Any]] = [
    {
        "name": "Aristocrats / Lebensverlust-Stapel",
        "beschreibung": (
            "Mehrere Karten ziehen Gegnern direkt Leben ab, wenn Kreaturen oder "
            "Tokens ins Spiel kommen, sterben oder das Spielfeld verlassen. Diese "
            "Trigger stapeln sich – jeder Kreatur-/Token-Effekt wird zu mehrfachem "
            "Schaden am Gegner."
        ),
        "payoff": r"each opponent loses",
        "enabler": None,
        "min": 2,
    },
    {
        "name": "Token-Engine",
        "beschreibung": (
            "Karten, die Tokens erzeugen, treffen auf Karten, die Tokens belohnen "
            "(beim Erscheinen, Verlassen oder Opfern). Zusammen entsteht eine sich "
            "selbst verstärkende Token-Maschine."
        ),
        "enabler": r"create[s]?\b[^.\n]*\btoken",
        "payoff": r"\btoken[^.\n]*(enter|leave|dies)|(create|sacrifice)[^.\n]*\btoken",
        "min": 2,
    },
    {
        "name": "+1/+1-Counter-Strategie",
        "beschreibung": (
            "Mehrere Karten verteilen oder nutzen +1/+1-Marken – eine gute Basis "
            "für Counter-Synergien und Proliferate."
        ),
        "payoff": r"\+1/\+1 counter",
        "enabler": None,
        "min": 2,
    },
    {
        "name": "Opfern & Todes-Trigger",
        "beschreibung": (
            "Ein Opfer-Auslass trifft auf Karten, die belohnen, wenn deine Kreaturen "
            "sterben. Du kannst Kreaturen gezielt opfern, um Effekte wiederholt "
            "auszulösen."
        ),
        "enabler": r"sacrifice (a|an|another|one|two|three|x|\d)[^.\n]*(creature|permanent|artifact|token)",
        "payoff": r"whenever [^.\n]*\bdies\b",
        "min": 2,
    },
    {
        "name": "Lebensgewinn-Synergie",
        "beschreibung": (
            "Karten, die Leben gewinnen, treffen auf Payoffs, die Lebensgewinn in "
            "Vorteile (Marken, Karten, Schaden) umwandeln."
        ),
        "enabler": r"\bgain(s)?\b[^.\n]*\blife\b|\blifelink\b",
        "payoff": r"whenever you gain(ed)? life|if you gained life",
        "min": 2,
    },
    {
        "name": "Friedhof-Recursion",
        "beschreibung": (
            "Mehrere Karten arbeiten mit dem Friedhof – Karten zurückholen, aus dem "
            "Friedhof wirken oder Friedhofs-Payoffs. Gutes Fundament für Value-Loops."
        ),
        "payoff": r"from your graveyard|from a graveyard",
        "enabler": None,
        "min": 3,
    },
]


def _card_texts(cards: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalisiert die Eingabe zu [{name, text}] mit kleingeschriebenem Oracle-Text."""
    out = []
    for c in cards:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        out.append({"name": name, "text": (c.get("oracle_text") or "").lower()})
    return out


def detect_synergies(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Findet Synergie-Themen in einer Kartenliste.

    Args:
        cards: Liste von Dicts mit mindestens 'name' und 'oracle_text'.

    Returns:
        Liste von {'theme', 'beschreibung', 'cards'} -- jeweils die beteiligten
        Kartennamen. Leere Liste, wenn keine Synergien gefunden wurden.
    """
    items = _card_texts(cards)
    if len(items) < 2:
        return []

    results: List[Dict[str, Any]] = []
    for theme in THEMES:
        payoff_re = re.compile(theme["payoff"], re.IGNORECASE) if theme.get("payoff") else None
        enabler_re = re.compile(theme["enabler"], re.IGNORECASE) if theme.get("enabler") else None

        payoff_cards = [it["name"] for it in items if payoff_re and payoff_re.search(it["text"])]

        if enabler_re is not None:
            enabler_cards = [it["name"] for it in items if enabler_re.search(it["text"])]
            if not payoff_cards or not enabler_cards:
                continue
            # Reihenfolge erhalten, Duplikate entfernen (dict.fromkeys)
            involved = list(dict.fromkeys(enabler_cards + payoff_cards))
        else:
            involved = list(dict.fromkeys(payoff_cards))

        if len(involved) >= theme.get("min", 2):
            results.append({
                "theme": theme["name"],
                "beschreibung": theme["beschreibung"],
                "cards": involved,
            })

    return results
