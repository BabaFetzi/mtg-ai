"""
tests/test_price_and_combos.py

Deckt zwei Bug-Fixes aus dem Qualitäts-Sweep ab:

1. Preis-Robustheit (services/scryfall.py):
   - best_market_price(): günstigster echter Preis statt 0.00, wenn der
     erste/gewählte Print keinen EUR-Preis hat (Sol Ring -> Secret Lair 0.00 €).
   - _build_card_info(): reichert fehlende Preise über den günstigsten Papier-Print
     an (Black Lotus -> Default-Print 'Vintage Masters' hat eur=null).

2. Combo-/Synergie-Scanner (services/combo_validation.py, routers/ai.py):
   - validate_combos(): verwirft halluzinierte (nicht existierende) oder im Format
     illegale KI-Combos.
   - run_combos_bg(): erzeugt keine erfundenen Fake-Combos ("<Karte> + Sol Ring")
     mehr, wenn keine echten Combos gefunden werden.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.scryfall import best_market_price, _pick_eur, _build_card_info
from services.combo_validation import split_combo_cards, validate_combos


# ======================================================================
# Preis-Helfer (rein)
# ======================================================================
def test_best_market_price_picks_cheapest_positive():
    assert best_market_price(["0.00", "1.19", "1.11", None, ""]) == "1.11"


def test_best_market_price_all_zero_or_missing_returns_zero():
    assert best_market_price(["0.00", None, "", "N/A"]) == "0.00"
    assert best_market_price([]) == "0.00"


def test_best_market_price_handles_comma_decimal():
    assert best_market_price(["1,21"]) == "1.21"


def test_pick_eur_prefers_eur_then_foil_then_none():
    assert _pick_eur({"eur": "5.00", "eur_foil": "9.00"}) == "5.00"
    assert _pick_eur({"eur": None, "eur_foil": "9.00"}) == "9.00"
    assert _pick_eur({"eur": None, "eur_foil": None, "eur_etched": "3.00"}) == "3.00"
    assert _pick_eur({"eur": None, "eur_foil": None}) is None
    assert _pick_eur({}) is None


# ======================================================================
# _build_card_info: Preis-Anreicherung über günstigsten Papier-Print
# ======================================================================
@pytest.mark.asyncio
async def test_build_card_info_enriches_missing_price():
    """Karte, deren Standard-Print keinen EUR-Preis hat (z.B. Black Lotus), muss
    über den günstigsten Papier-Print einen realen Preis erhalten -- nicht 0.00."""
    card_data = {"name": "Black Lotus", "prices": {"eur": None, "eur_foil": None}, "type_line": "Artifact"}

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [
        {"prices": {"eur": "22454.09"}},
        {"prices": {"eur": "11005.15"}},   # günstigster
        {"prices": {"eur": None}},
    ]}
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    info = await _build_card_info(client, card_data)

    assert info["price"] == "11005.15"
    assert info["prices"]["eur"] == "11005.15"
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_card_info_keeps_existing_price_without_extra_call():
    """Hat der Standard-Print bereits einen EUR-Preis, darf KEIN zusätzlicher
    Scryfall-Call erfolgen (Performance im Batch-Pfad)."""
    card_data = {"name": "Sol Ring", "prices": {"eur": "1.21"}, "type_line": "Artifact"}
    client = MagicMock()
    client.get = AsyncMock()

    info = await _build_card_info(client, card_data)

    assert info["price"] == "1.21"
    client.get.assert_not_called()


# ======================================================================
# Combo-Namens-Parsing
# ======================================================================
def test_split_combo_cards():
    assert split_combo_cards("A + B") == ["A", "B"]
    assert split_combo_cards(
        "Kiki-Jiki, Mirror Breaker + Zealous Conscripts"
    ) == ["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"]
    assert split_combo_cards("A+B+C") == ["A", "B", "C"]
    assert split_combo_cards("") == []
    assert split_combo_cards("   ") == []


# ======================================================================
# validate_combos: Halluzinations-Filter
# ======================================================================
def _scryfall_stub():
    return {
        "kiki-jiki, mirror breaker": {"name": "Kiki-Jiki, Mirror Breaker", "legalities": {"commander": "legal"}},
        "zealous conscripts": {"name": "Zealous Conscripts", "legalities": {"commander": "legal"}},
        "grizzly bears": {"name": "Grizzly Bears", "legalities": {"commander": "legal"}},
        "channel": {"name": "Channel", "legalities": {"commander": "banned", "vintage": "restricted"}},
    }


@pytest.mark.asyncio
async def test_validate_combos_drops_nonexistent_card(monkeypatch):
    monkeypatch.setattr(
        "services.combo_validation.fetch_card_details_cached",
        AsyncMock(return_value=_scryfall_stub()),
    )
    combos = [
        {"name": "Kiki-Jiki, Mirror Breaker + Zealous Conscripts", "grund": "echt"},
        {"name": "Grizzly Bears + Frobnicator Prime", "grund": "erfunden"},  # 2. Karte existiert nicht
    ]
    valide, verworfen = await validate_combos(combos, "commander")

    assert [c["name"] for c in valide] == ["Kiki-Jiki, Mirror Breaker + Zealous Conscripts"]
    assert valide[0]["verifiziert"] is True
    assert len(verworfen) == 1
    assert "existiert nicht" in verworfen[0]["grund_verworfen"].lower()


@pytest.mark.asyncio
async def test_validate_combos_drops_format_illegal_card(monkeypatch):
    monkeypatch.setattr(
        "services.combo_validation.fetch_card_details_cached",
        AsyncMock(return_value=_scryfall_stub()),
    )
    # Channel ist in Commander gebannt -> Combo muss verworfen werden.
    combos = [{"name": "Channel + Grizzly Bears", "grund": "illegal im Format"}]
    valide, verworfen = await validate_combos(combos, "commander")

    assert valide == []
    assert len(verworfen) == 1
    assert "nicht legal" in verworfen[0]["grund_verworfen"].lower()


@pytest.mark.asyncio
async def test_validate_combos_required_card_must_be_present(monkeypatch):
    monkeypatch.setattr(
        "services.combo_validation.fetch_card_details_cached",
        AsyncMock(return_value=_scryfall_stub()),
    )
    combos = [{"name": "Kiki-Jiki, Mirror Breaker + Zealous Conscripts", "grund": "x"}]
    # required_card ist NICHT Teil der Combo -> verworfen.
    valide, verworfen = await validate_combos(combos, "commander", required_card="Grizzly Bears")
    assert valide == []
    assert len(verworfen) == 1


@pytest.mark.asyncio
async def test_validate_combos_fail_open_when_scryfall_unavailable(monkeypatch):
    """Scryfall-Ausfall soll das Feature nicht abschalten: Combos durchlassen,
    aber nicht als verifiziert markieren."""
    monkeypatch.setattr(
        "services.combo_validation.fetch_card_details_cached",
        AsyncMock(side_effect=Exception("Scryfall down")),
    )
    combos = [{"name": "A + B", "grund": "x"}]
    valide, verworfen = await validate_combos(combos, "commander")
    assert len(valide) == 1
    assert valide[0]["verifiziert"] is False
    assert verworfen == []


@pytest.mark.asyncio
async def test_validate_combos_empty_input():
    assert await validate_combos([], "commander") == ([], [])


# ======================================================================
# run_combos_bg: keine erfundenen Fake-Combos mehr
# ======================================================================
@pytest.mark.asyncio
async def test_run_combos_bg_no_fake_fallback(monkeypatch):
    """Für eine Karte ohne echte Combos (Spellbook leer, Gemini aus) muss das
    Ergebnis leer sein -- NICHT die früheren Fake-Combos '<Karte> + Sol Ring'."""
    import httpx
    import routers.ai as ai

    # Commander Spellbook liefert nichts
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": []}
    monkeypatch.setattr(httpx, "get", MagicMock(return_value=resp))

    # Scryfall-Namensauflösung
    monkeypatch.setattr(
        "services.scryfall.fetch_card_details_cached",
        AsyncMock(return_value={"grizzly bears": {"name": "Grizzly Bears"}}),
    )
    # Gemini deaktiviert
    monkeypatch.setattr(ai, "model_lite", None)

    # Cache-set abfangen
    captured = {}
    monkeypatch.setattr(ai.scryfall_cache, "set", lambda k, v: captured.__setitem__("result", v))

    # DB-Session mocken
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(ai, "get_db_session", lambda: cm)

    await ai.run_combos_bg("job-1", "Grizzly Bears", "commander", "combos:grizzly bears:commander")

    assert captured["result"] == {"empfehlungen": []}
