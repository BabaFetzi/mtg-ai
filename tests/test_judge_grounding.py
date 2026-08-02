"""
tests/test_judge_grounding.py – Judge-Antworten an echten Kartendaten erden (T-5.1)

Der Judge hat zuvor Kartentexte erfunden, weil die Frage ohne jeden Kontext an
das Modell ging. Diese Tests sichern ab, dass

1. in der Frage genannte Karten erkannt und bei Scryfall aufgelöst werden,
2. der echte Regeltext im Prompt landet,
3. nicht auffindbare Karten explizit als "nicht gefunden" markiert werden,
4. das Modell angewiesen wird, nichts zu erfinden.
"""

from unittest.mock import patch

import pytest

from routers.ai import _build_judge_prompt
from services.scryfall import extract_card_name_candidates


# ----------------------------------------------------------------------
# Kandidaten-Extraktion
# ----------------------------------------------------------------------
def test_extracts_quoted_and_capitalized_card_names():
    kandidaten = extract_card_name_candidates(
        'Was passiert wenn ich "Sol Ring" und Krenko, Mob Boss zusammen spiele?'
    )
    assert "Sol Ring" in kandidaten
    assert "Krenko, Mob Boss" in kandidaten


def test_generic_german_words_are_not_treated_as_cards():
    """Eine reine Regelfrage ohne Karten darf keine Scryfall-Abfragen auslösen."""
    assert extract_card_name_candidates("Wie funktioniert der Stapel?") == []


def test_candidate_count_is_bounded():
    frage = " ".join(f"Karte Alpha{i} Beta{i}" for i in range(20))
    assert len(extract_card_name_candidates(frage, max_candidates=4)) <= 4


# ----------------------------------------------------------------------
# Prompt-Aufbau
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prompt_contains_real_oracle_text_of_resolved_card():
    async def fake_fetch(names):
        return {
            "sol ring": {
                "name": "Sol Ring",
                "type": "Artifact",
                "oracle_text": "{T}: Add {C}{C}.",
            }
        }

    with patch("routers.ai.fetch_card_details_cached", fake_fetch):
        prompt = await _build_judge_prompt('Wie funktioniert "Sol Ring"?')

    assert "Sol Ring" in prompt
    assert "{T}: Add {C}{C}." in prompt
    assert "Erfinde NIEMALS" in prompt


@pytest.mark.asyncio
async def test_unresolved_card_is_flagged_instead_of_invented():
    """Kernfall des gemeldeten Bugs: eine Karte, die Scryfall nicht kennt, muss
    ausdrücklich als unbekannt markiert werden -- damit das Modell nachfragt."""
    async def fake_fetch(names):
        return {}

    with patch("routers.ai.fetch_card_details_cached", fake_fetch):
        prompt = await _build_judge_prompt("Wie wird Loot der Pfadfinder gespielt?")

    assert "NICHT BEI SCRYFALL GEFUNDEN" in prompt
    assert "nachfragen" in prompt


@pytest.mark.asyncio
async def test_prompt_still_built_when_scryfall_fails():
    """Fällt Scryfall aus, antwortet der Judge weiterhin -- nur ohne Kartenkontext."""
    async def boom(names):
        raise RuntimeError("Scryfall down")

    with patch("routers.ai.fetch_card_details_cached", boom):
        prompt = await _build_judge_prompt('Wie funktioniert "Sol Ring"?')

    assert "FRAGE:" in prompt
    assert "Erfinde NIEMALS" in prompt
