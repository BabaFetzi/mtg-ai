"""
tests/test_search_suggestions.py – Vorschläge statt Sackgasse bei der Kartensuche

Anlass: Deutsche Kartennamen aus brandneuen Sets (z.B. "Azog, Morias Untergang"
aus dem Hobbit-Set) sind bei Scryfall noch nicht hinterlegt -- die Suche endete
in einem "Karte nicht gefunden"-Popup ohne jede Hilfe.

Wichtig: Es darf NIE automatisch eine andere Karte ausgeliefert werden. Genau
daraus entstand früher der Fehler, dass eine nicht besessene Karte als Treffer
erschien. Es gibt ausschliesslich Vorschläge zum Anklicken.
"""

from unittest.mock import patch

import pytest

from routers.cards import _suchbausteine, _finde_vorschlaege


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


# ----------------------------------------------------------------------
# Zerlegung in Suchbausteine
# ----------------------------------------------------------------------
def test_splits_german_compound_names():
    """Deutsche Kartennamen sind oft zusammengesetzt."""
    bausteine = _suchbausteine("Furchterregendes Goblin-Duo")
    assert "Goblin" in bausteine
    assert "Furchterregendes" in bausteine


def test_proper_noun_is_kept():
    assert "Azog" in _suchbausteine("Azog, Morias Untergang")


def test_filler_words_are_dropped():
    bausteine = _suchbausteine("Der Untergang von Moria")
    assert "der" not in [b.lower() for b in bausteine]
    assert "von" not in [b.lower() for b in bausteine]


def test_candidates_are_bounded():
    assert len(_suchbausteine("Eins Zwei Drei Vier Fuenf Sechs Sieben")) <= 3


# ----------------------------------------------------------------------
# Vorschläge
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_proper_noun_leads_to_the_real_card():
    """Kernfall: 'Azog, Morias Untergang' -> Vorschlag "Azog, Moria's Ruin"."""
    async def fake_request(client, method, url, **kw):
        if "Azog" in url:
            return FakeResponse(200, {"data": ["Azog, Moria's Ruin"]})
        return FakeResponse(200, {"data": []})

    with patch("routers.cards.scryfall_request", fake_request):
        vorschlaege = await _finde_vorschlaege(None, "Azog, Morias Untergang")

    assert "Azog, Moria's Ruin" in vorschlaege


@pytest.mark.asyncio
async def test_generic_word_is_not_turned_into_noise():
    """Ein sehr allgemeines Wort ('Goblin') liefert zwanzig Treffer -- die wären
    als Vorschlag wertlos und werden verworfen."""
    def _abfrage(url):
        import urllib.parse
        return urllib.parse.unquote(url.split("q=", 1)[1])

    async def fake_request(client, method, url, **kw):
        # Nur die Abfrage GENAU "Goblin" liefert die vielen Treffer -- der
        # vollständige Begriff findet wie in der Realität nichts.
        if _abfrage(url) == "Goblin":
            return FakeResponse(200, {"data": [f"Goblin {i}" for i in range(20)]})
        return FakeResponse(200, {"data": []})

    with patch("routers.cards.scryfall_request", fake_request):
        vorschlaege = await _finde_vorschlaege(None, "Furchterregendes Goblin-Duo")

    assert vorschlaege == []


@pytest.mark.asyncio
async def test_suggestions_are_capped():
    async def fake_request(client, method, url, **kw):
        return FakeResponse(200, {"data": [f"Karte {i}" for i in range(8)]})

    with patch("routers.cards.scryfall_request", fake_request):
        vorschlaege = await _finde_vorschlaege(None, "Irgendein Suchbegriff", limit=4)

    assert len(vorschlaege) <= 4


@pytest.mark.asyncio
async def test_scryfall_failure_yields_no_suggestions_not_an_error():
    async def boom(client, method, url, **kw):
        raise RuntimeError("offline")

    with patch("routers.cards.scryfall_request", boom):
        assert await _finde_vorschlaege(None, "Azog") == []
