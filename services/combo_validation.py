"""
services/combo_validation.py – Validierung von KI-generierten Combos gegen echte
Kartendaten (Scryfall).

Motivation (siehe Bug-Report "KI halluziniert Combos"):
Der Synergie-/Combo-Scanner mischt Ergebnisse aus drei Quellen:
  1. lokale Combo-Datenbank (services.combos)      -> vertrauenswürdig
  2. Commander Spellbook API (echte Combo-Datenbank) -> vertrauenswürdig
  3. Google Gemini (nur als Fallback)                -> NICHT vertrauenswürdig

Die KI (Quelle 3) kann Karten erfinden ("Grizzly Bears + Time Vault") oder Combos
ausgeben, die im gewählten Format illegal sind. Dieses Modul prüft solche Combos
gegen Scryfall:
  - Existenz:        Jede im Combo-Namen referenzierte Karte muss real existieren.
  - Format-Legalität: Jede Karte muss im angegebenen Format legal/restricted sein.
  - required_card:    (optional) die abgefragte Karte muss Teil der Combo sein.

Nicht verifizierbare Combos werden verworfen (mit Log-Eintrag), statt sie dem
Nutzer als Fakt zu präsentieren.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set, Tuple

from services.scryfall import fetch_card_details_cached

logger = logging.getLogger(__name__)

# Scryfall-Legalitätszustände, die als "im Format spielbar" gelten.
_LEGAL_STATES = {"legal", "restricted"}


def split_combo_cards(combo_name: str) -> List[str]:
    """Zerlegt einen Combo-Namen wie
    'Kiki-Jiki, Mirror Breaker + Zealous Conscripts' in die einzelnen Kartennamen.
    Trennt an '+' (mit optionalem Whitespace). Kommas innerhalb eines Kartennamens
    bleiben erhalten."""
    if not combo_name:
        return []
    parts = re.split(r"\s*\+\s*", combo_name.strip())
    return [p.strip() for p in parts if p.strip()]


async def validate_combos(
    combos: List[Dict[str, Any]],
    format_name: str = "commander",
    required_card: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validiert eine Liste von Combos gegen Scryfall.

    Args:
        combos: Liste von Dicts mit mindestens dem Schlüssel 'name'
                (Format "Karte A + Karte B [+ Karte C]").
        format_name: MTG-Format für die Legalitätsprüfung (z.B. 'commander').
        required_card: Falls gesetzt, muss diese Karte in jeder Combo vorkommen
                       (für Einzelkarten-Combo-Suche).

    Returns:
        (valide, verworfen) – valide Combos erhalten 'verifiziert': True,
        verworfene erhalten 'grund_verworfen'.
    """
    if not combos:
        return [], []

    # Alle referenzierten Kartennamen einsammeln und in EINEM Batch auflösen.
    per_combo_cards: List[List[str]] = []
    all_names: Set[str] = set()
    for combo in combos:
        cards = split_combo_cards(combo.get("name", ""))
        per_combo_cards.append(cards)
        all_names.update(cards)

    try:
        scryfall_data = await fetch_card_details_cached(list(all_names)) if all_names else {}
    except Exception:
        # Fail-open: Ohne Scryfall-Daten kann nicht validiert werden. Wir lassen die
        # Combos durch, markieren sie aber NICHT als verifiziert, statt sie fälschlich
        # zu verwerfen (ein Scryfall-Ausfall soll das Feature nicht abschalten).
        logger.warning("Combo-Validierung übersprungen (Scryfall nicht erreichbar)", exc_info=True)
        passthrough = []
        for combo in combos:
            c = dict(combo)
            c.setdefault("verifiziert", False)
            passthrough.append(c)
        return passthrough, []

    fmt = (format_name or "").lower().strip()
    req_lower = required_card.lower().strip() if required_card else None

    valide: List[Dict[str, Any]] = []
    verworfen: List[Dict[str, Any]] = []

    for combo, cards in zip(combos, per_combo_cards):
        result = dict(combo)

        if not cards:
            result["grund_verworfen"] = "Kein Kartenname im Combo-Namen erkennbar"
            verworfen.append(result)
            continue

        problem: Optional[str] = None
        resolved_lower: Set[str] = set()

        for card in cards:
            info = scryfall_data.get(card.lower().strip())
            if not info:
                problem = f"Karte existiert nicht: '{card}'"
                break
            resolved_lower.add(str(info.get("name", card)).lower().strip())

            # Format-Legalität: nur bestrafen, wenn Scryfall eine Angabe hat und
            # diese 'nicht legal'/'banned' lautet (fehlende Angabe -> nicht bestrafen).
            state = (info.get("legalities") or {}).get(fmt)
            if state is not None and state not in _LEGAL_STATES:
                problem = f"'{info.get('name', card)}' ist in '{format_name}' nicht legal ({state})"
                break

        if problem is None and req_lower:
            card_forms = resolved_lower | {c.lower().strip() for c in cards}
            if req_lower not in card_forms:
                problem = f"Abgefragte Karte '{required_card}' ist nicht Teil der Combo"

        if problem is None:
            result["verifiziert"] = True
            valide.append(result)
        else:
            result["grund_verworfen"] = problem
            verworfen.append(result)
            logger.info("KI-Combo verworfen (%s): %r", problem, combo.get("name"))

    return valide, verworfen
