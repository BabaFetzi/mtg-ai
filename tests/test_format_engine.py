import pytest
from format_engine import FormatValidator, parse_deck_liste

# Mock database provider
async def mock_card_details_provider(names):
    details = {}
    for name in names:
        n_lower = name.lower().strip()
        if "sol ring" in n_lower:
            details[n_lower] = {
                "name": "Sol Ring",
                "type": "Artifact",
                "colors": [],
                "color_identity": [],
                "cmc": 1.0,
                "rarity": "uncommon",
                "legalities": {"commander": "legal", "standard": "not_legal", "vintage": "legal"}
            }
        elif "lightning bolt" in n_lower:
            details[n_lower] = {
                "name": "Lightning Bolt",
                "type": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 1.0,
                "rarity": "common",
                "legalities": {"commander": "legal", "standard": "not_legal", "modern": "legal", "vintage": "legal"}
            }
        elif "mountain" in n_lower:
            details[n_lower] = {
                "name": "Mountain",
                "type": "Basic Land",
                "colors": [],
                "color_identity": ["R"],
                "cmc": 0.0,
                "rarity": "common",
                "legalities": {"commander": "legal", "standard": "legal", "modern": "legal", "vintage": "legal"}
            }
        elif "forest" in n_lower:
            details[n_lower] = {
                "name": "Forest",
                "type": "Basic Land",
                "colors": [],
                "color_identity": ["G"],
                "cmc": 0.0,
                "rarity": "common",
                "legalities": {"commander": "legal", "standard": "legal", "modern": "legal", "vintage": "legal"}
            }
        elif "krenko, mob boss" in n_lower:
            details[n_lower] = {
                "name": "Krenko, Mob Boss",
                "type": "Legendary Creature — Goblin Warrior",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 4.0,
                "rarity": "rare",
                "legalities": {"commander": "legal", "standard": "not_legal"}
            }
        elif "black lotus" in n_lower:
            details[n_lower] = {
                "name": "Black Lotus",
                "type": "Artifact",
                "colors": [],
                "color_identity": [],
                "cmc": 0.0,
                "rarity": "rare",
                "legalities": {"commander": "banned", "standard": "not_legal", "vintage": "restricted"}
            }
    return details

@pytest.mark.asyncio
async def test_parse_deck_liste():
    deck_text = """
    # My Awesome Deck
    1 Sol Ring
    4 Lightning Bolt
    58 Mountain
    """
    parsed = parse_deck_liste(deck_text)
    assert len(parsed) == 3
    assert parsed[0] == (1, "Sol Ring")
    assert parsed[1] == (4, "Lightning Bolt")
    assert parsed[2] == (58, "Mountain")

@pytest.mark.asyncio
async def test_validate_standard_illegal_too_few_cards():
    deck_text = "4 Lightning Bolt\n10 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "standard", mock_card_details_provider)
    assert res.legal is False
    assert any("mindestens 60 Karten" in err for err in res.errors)

@pytest.mark.asyncio
async def test_validate_standard_illegal_too_many_copies():
    # 5 Lightning Bolts (max is 4)
    deck_text = "5 Lightning Bolt\n55 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "modern", mock_card_details_provider)
    assert res.legal is False
    assert any("maximal 4 Kopien" in err for err in res.errors)

@pytest.mark.asyncio
async def test_validate_commander_legal():
    # 1 Commander + 99 other cards (1 Sol Ring + 98 Mountain) = 100 cards
    deck_text = "1 Krenko, Mob Boss\n1 Sol Ring\n98 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "commander", mock_card_details_provider)
    assert res.legal is True
    assert len(res.errors) == 0

@pytest.mark.asyncio
async def test_validate_commander_illegal_color_identity():
    # Krenko is Red. Forest has Green color identity -> Illegal.
    deck_text = "1 Krenko, Mob Boss\n1 Forest\n98 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "commander", mock_card_details_provider)
    assert res.legal is False
    assert any("illegale Farben" in err for err in res.errors)
    assert any("Forest" in err for err in res.errors)

@pytest.mark.asyncio
async def test_validate_commander_illegal_multiple_copies():
    # Sol Ring cannot have 2 copies in Commander
    deck_text = "1 Krenko, Mob Boss\n2 Sol Ring\n97 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "commander", mock_card_details_provider)
    assert res.legal is False
    assert any("Singleton-Format" in err for err in res.errors)

@pytest.mark.asyncio
async def test_validate_vintage_restricted():
    # Black Lotus is restricted in Vintage (max 1 copy)
    deck_text = "2 Black Lotus\n58 Mountain"
    res = await FormatValidator.validate_deck(deck_text, "vintage", mock_card_details_provider)
    assert res.legal is False
    assert any("limitiert (restricted)" in err for err in res.errors)
