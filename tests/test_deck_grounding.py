"""
tests/test_deck_grounding.py – Deck-Analyse an echten Kartendaten erden

Bisher bekam die KI-Deck-Analyse nur die nackte Namensliste und musste jeden
Kartentext aus dem Gedächtnis rekonstruieren -- bei unbekannten Karten hat sie
ihn erfunden. Diese Tests sichern ab, dass echte Scryfall-Daten im Prompt landen.
"""

from unittest.mock import patch

import pytest

import services.scryfall as sf
from routers.decks import _fakten_abschnitt, _deck_fakten


# ----------------------------------------------------------------------
# Faktenbeschaffung
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_build_deck_card_facts_contains_real_oracle_text():
    async def fake_fetch(names):
        return {
            "lightning bolt": {
                "name": "Lightning Bolt",
                "type": "Instant",
                "mana_cost": "{R}",
                "cmc": 1.0,
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            }
        }

    with patch.object(sf, "fetch_card_details_cached", fake_fetch):
        fakten, fehlend = await sf.build_deck_card_facts("4x Lightning Bolt")

    assert "4x Lightning Bolt" in fakten
    assert "Instant" in fakten
    assert "{R}" in fakten
    assert "deals 3 damage to any target" in fakten
    assert fehlend == []


@pytest.mark.asyncio
async def test_quantities_are_summed_per_card():
    async def fake_fetch(names):
        return {"sol ring": {"name": "Sol Ring", "type": "Artifact", "oracle_text": "{T}: Add {C}{C}."}}

    with patch.object(sf, "fetch_card_details_cached", fake_fetch):
        fakten, _ = await sf.build_deck_card_facts("2 Sol Ring\n1 Sol Ring")

    assert "3x Sol Ring" in fakten


@pytest.mark.asyncio
async def test_unresolvable_cards_are_reported_not_invented():
    async def fake_fetch(names):
        return {}

    with patch.object(sf, "fetch_card_details_cached", fake_fetch):
        fakten, fehlend = await sf.build_deck_card_facts("1 Loot, the Pathfinder")

    assert fakten == ""
    assert "Loot, the Pathfinder" in fehlend


@pytest.mark.asyncio
async def test_card_count_is_bounded():
    """Kosten-/Token-Schutz: sehr grosse Listen werden gedeckelt."""
    aufgeloeste = {}

    async def fake_fetch(names):
        aufgeloeste["anzahl"] = len(names)
        return {}

    # Bewusst ohne Leerzeichen vor der Zahl: clean_card_name entfernt eine
    # nachgestellte " 12", wodurch alle Namen sonst zu "Karte" kollabieren.
    deck = "\n".join(f"1 Testkarte{i}" for i in range(300))
    with patch.object(sf, "fetch_card_details_cached", fake_fetch):
        await sf.build_deck_card_facts(deck, max_cards=100)

    assert aufgeloeste["anzahl"] == 100


@pytest.mark.asyncio
async def test_empty_decklist_is_handled():
    fakten, fehlend = await sf.build_deck_card_facts("")
    assert fakten == ""
    assert fehlend == []


# ----------------------------------------------------------------------
# Prompt-Abschnitt
# ----------------------------------------------------------------------
def test_fakten_abschnitt_forbids_inventing():
    text = _fakten_abschnitt("1x Sol Ring — Artifact\n  Regeltext: {T}: Add {C}{C}.", [])
    assert "Erfinde keine Kartentexte" in text
    assert "BESTÄTIGTE KARTENDATEN" in text


def test_fakten_abschnitt_lists_unresolved_cards():
    text = _fakten_abschnitt("", ["Loot, the Pathfinder"])
    assert "NICHT AUFLÖSBAR" in text
    assert "Loot, the Pathfinder" in text


def test_fakten_abschnitt_empty_when_nothing_known():
    assert _fakten_abschnitt("", []) == ""


@pytest.mark.asyncio
async def test_deck_analysis_survives_scryfall_outage():
    """Fällt Scryfall aus, muss die Analyse trotzdem laufen -- nur ohne Fakten."""
    async def boom(deck_liste, max_cards=100):
        raise RuntimeError("Scryfall down")

    with patch("routers.decks.build_deck_card_facts", boom):
        fakten, fehlend = await _deck_fakten("1 Sol Ring")

    assert fakten == ""
    assert fehlend == []
