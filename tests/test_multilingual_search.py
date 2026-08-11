"""
tests/test_multilingual_search.py – Karten in beliebiger Sprache finden

Ziel: Egal in welcher gedruckten Sprache ein Kartenname eingegeben wird, die
Karte muss gefunden werden -- und zwar die RICHTIGE.

Zwei Ebenen:
1. Exakter Abgleich des gedruckten Namens (funktioniert für alle Sets, für die
   Scryfall lokalisierte Daten hat -- praktisch alle ausser brandneuen).
2. Übersetzung durch das Modell mit Bestätigung durch Scryfall (greift, wenn es
   noch gar keine lokalisierten Daten gibt, z.B. in der Release-Woche).

Sicherheitsprinzip: Ein Modellvorschlag wird NIE direkt ausgeliefert. Nur was
Scryfall als reale Karte bestätigt, zählt.
"""

from unittest.mock import patch

import pytest

import services.multilingual_search as ml
from routers.cards import _namensschluessel, _fallback_lang_search


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeCache:
    def __init__(self):
        self.daten = {}

    def get(self, key):
        return self.daten.get(key)

    def set(self, key, value):
        self.daten[key] = value


# ----------------------------------------------------------------------
# Namensnormalisierung
# ----------------------------------------------------------------------
def test_typographic_apostrophes_are_equalised():
    assert _namensschluessel("Moria’s Ruin") == _namensschluessel("Moria's Ruin")


def test_case_and_whitespace_are_ignored():
    assert _namensschluessel("  LIGHTNING   BOLT ") == _namensschluessel("Lightning Bolt")


def test_diacritics_are_preserved():
    """Relámpago und Relampago sind unterschiedliche Zeichenfolgen -- der
    exakte Abgleich soll nicht zu grosszügig werden."""
    assert _namensschluessel("Relámpago") != _namensschluessel("Relampago")


# ----------------------------------------------------------------------
# Exakter Abgleich des gedruckten Namens
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exact_printed_name_wins_over_first_result():
    """Kernfehler: Scryfall sucht mit name:"..." als TEILSTRING und sortiert
    nach Relevanz. "Fulmine" (italienisch für Lightning Bolt) lieferte deshalb
    "Arc Lightning" (italienisch "Fulmine ad Arco")."""
    treffer = {
        "data": [
            {"name": "Arc Lightning", "printed_name": "Fulmine ad Arco"},
            {"name": "Lightning Bolt", "printed_name": "Fulmine"},
        ]
    }
    aufgerufen = {}

    async def fake_request(client, method, url, **kw):
        if "/search" in url:
            return FakeResponse(200, treffer)
        aufgerufen["named"] = url
        return FakeResponse(200, {"name": "Lightning Bolt"})

    with patch("routers.cards.scryfall_request", fake_request):
        resp = await _fallback_lang_search(None, "Fulmine", FakeResponse(404))

    assert resp.status_code == 200
    assert "Lightning" in aufgerufen["named"]


@pytest.mark.asyncio
async def test_no_exact_match_and_ambiguous_yields_nothing():
    """Lieber nichts als die falsche Karte."""
    treffer = {"data": [
        {"name": "Arc Lightning", "printed_name": "Fulmine ad Arco"},
        {"name": "Ball Lightning", "printed_name": "Fulmine Globulare"},
    ]}

    async def fake_request(client, method, url, **kw):
        return FakeResponse(200, treffer)

    original = FakeResponse(404)
    with patch("routers.cards.scryfall_request", fake_request):
        resp = await _fallback_lang_search(None, "Fulmine", original)

    assert resp is original, "Bei Mehrdeutigkeit darf nicht geraten werden"


@pytest.mark.asyncio
async def test_single_unambiguous_result_is_accepted():
    """Kein exakter Treffer, aber die Suche meint eindeutig eine Karte."""
    treffer = {"data": [
        {"name": "Taster of Wares", "printed_name": "Plunderprüfer"},
        {"name": "Taster of Wares", "printed_name": "Taster of Wares"},
    ]}

    async def fake_request(client, method, url, **kw):
        if "/search" in url:
            return FakeResponse(200, treffer)
        return FakeResponse(200, {"name": "Taster of Wares"})

    with patch("routers.cards.scryfall_request", fake_request):
        resp = await _fallback_lang_search(None, "Plunderpruefer", FakeResponse(404))

    assert resp.status_code == 200


# ----------------------------------------------------------------------
# Übersetzung mit Bestätigung
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def cache():
    fake = FakeCache()
    with patch.object(ml, "scryfall_cache", fake):
        yield fake


@pytest.mark.asyncio
async def test_translation_is_confirmed_by_scryfall():
    """Der reale Fall: literale Übersetzung trifft über die Fuzzy-Suche."""
    async def kandidaten(begriff):
        return ["Fearsome Goblin Duo", "Terrifying Goblin Pair"]

    async def fake_request(client, method, url, **kw):
        if "Fearsome+Goblin+Duo" in url or "Fearsome%20Goblin%20Duo" in url:
            return FakeResponse(200, {"name": "Fearsome Goblin Pair"})
        return FakeResponse(404)

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        karte = await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo")

    assert karte["name"] == "Fearsome Goblin Pair"


@pytest.mark.asyncio
async def test_hallucinated_card_is_rejected():
    """Erfindet das Modell eine Karte, bestätigt Scryfall sie nicht -- und es
    darf NICHTS ausgeliefert werden."""
    async def kandidaten(begriff):
        return ["Totally Made Up Card", "Another Invention"]

    async def fake_request(client, method, url, **kw):
        return FakeResponse(404)

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        assert await ml.finde_karte_sprachunabhaengig(None, "Irgendein Fantasiename") is None


@pytest.mark.asyncio
async def test_result_is_cached_so_model_runs_once(cache):
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Fearsome Goblin Duo"]

    async def fake_request(client, method, url, **kw):
        return FakeResponse(200, {"name": "Fearsome Goblin Pair"})

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo")
        await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo")

    assert aufrufe["n"] == 1, "Dieselbe Eingabe darf nur EINEN Modellaufruf kosten"


@pytest.mark.asyncio
async def test_negative_result_is_cached_too(cache):
    """Auch ein erfolgloser Begriff darf das Modell nicht wiederholt kosten."""
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Nichts Passendes"]

    async def fake_request(client, method, url, **kw):
        return FakeResponse(404)

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        await ml.finde_karte_sprachunabhaengig(None, "Unauffindbarer Kartenname")
        await ml.finde_karte_sprachunabhaengig(None, "Unauffindbarer Kartenname")

    assert aufrufe["n"] == 1


@pytest.mark.asyncio
async def test_negative_cache_expires_so_a_card_is_not_lost_for_a_day(cache):
    """Regression: der Fehlschlag wurde 24 h gemerkt. Lief der Server beim
    ersten Versuch ohne API-Schlüssel, blieb die Karte danach einen ganzen Tag
    unauffindbar -- obwohl längst alles korrekt konfiguriert war."""
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Fearsome Goblin Duo"]

    gefunden = {"ja": False}

    async def fake_request(client, method, url, **kw):
        if gefunden["ja"]:
            return FakeResponse(200, {"name": "Fearsome Goblin Pair"})
        return FakeResponse(404)

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        assert await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo") is None

        # Cache-Eintrag künstlich altern lassen.
        for eintrag in cache.daten.values():
            eintrag["zeit"] -= ml.NEGATIV_CACHE_SEKUNDEN + 1

        gefunden["ja"] = True
        karte = await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo")

    assert aufrufe["n"] == 2, "Nach Ablauf muss erneut gefragt werden"
    assert karte["name"] == "Fearsome Goblin Pair"


@pytest.mark.asyncio
async def test_missing_model_is_not_remembered_as_a_failure(cache):
    """Fehlt das Sprachmodell (z.B. kein GEMINI_API_KEY), ist das ein
    technischer Ausfall -- kein Beweis, dass es die Karte nicht gibt. Er darf
    den späteren, korrekt konfigurierten Versuch nicht blockieren."""
    async def kein_modell(begriff):
        return []

    async def fake_request(client, method, url, **kw):
        return FakeResponse(200, {"name": "Fearsome Goblin Pair"})

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kein_modell):
        assert await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo") is None

    assert cache.daten == {}, "Ein technischer Ausfall darf nichts zementieren"

    async def kandidaten(begriff):
        return ["Fearsome Goblin Duo"]

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", fake_request):
        karte = await ml.finde_karte_sprachunabhaengig(None, "Furchterregendes Goblin-Duo")

    assert karte["name"] == "Fearsome Goblin Pair"


@pytest.mark.asyncio
async def test_missing_model_is_logged(caplog):
    """Die Stufe darf nicht stumm aussteigen -- sonst ist im Betrieb nicht
    erkennbar, WARUM eine Karte nicht gefunden wurde."""
    import logging

    with patch("services.ai_service.model_lite", None), \
         caplog.at_level(logging.WARNING, logger="services.multilingual_search"):
        assert await ml._frage_modell_nach_englischen_namen("Furchterregendes Goblin-Duo") == []

    assert "kein Sprachmodell" in caplog.text


@pytest.mark.asyncio
async def test_gibberish_does_not_trigger_a_model_call():
    """Kostenschutz: Unsinnseingaben lösen keinen Modellaufruf aus."""
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return []

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten):
        for unsinn in ["xy", "?!", "   ", "a"]:
            assert await ml.finde_karte_sprachunabhaengig(None, unsinn) is None

    assert aufrufe["n"] == 0


@pytest.mark.asyncio
async def test_can_be_disabled():
    with patch.object(ml, "UEBERSETZUNGSSUCHE_AKTIV", False):
        assert await ml.finde_karte_sprachunabhaengig(None, "Blitzschlag") is None
