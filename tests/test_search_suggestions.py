"""
tests/test_search_suggestions.py – Vorschläge statt Sackgasse bei der Kartensuche

Anlass: Deutsche Kartennamen aus brandneuen Sets (z.B. "Azog, Morias Untergang"
aus dem Hobbit-Set) sind bei Scryfall noch nicht hinterlegt -- die Suche endete
in einem "Karte nicht gefunden"-Popup ohne jede Hilfe.

Wichtig: Es darf NIE automatisch eine andere Karte ausgeliefert werden. Genau
daraus entstand früher der Fehler, dass eine nicht besessene Karte als Treffer
erschien. Es gibt ausschliesslich Vorschläge zum Anklicken.
"""

import urllib.parse
from unittest.mock import patch

import pytest

from routers.cards import _suchbausteine, _finde_vorschlaege


class _LeererCache:
    """Cache-Double: liefert nie einen Treffer, merkt sich Schreibvorgänge."""

    def get(self, key):
        return None

    def set(self, key, value):
        pass


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


# ======================================================================
# Alchemy-Fassungen ausblenden
# ======================================================================
def _anfrage():
    """Minimale echte Request.

    Der Endpunkt ist inzwischen gedrosselt (slowapi), und der Dekorator
    besteht auf einer echten starlette-Request. Beim direkten Aufruf der
    Funktion -- also unter Umgehung von FastAPI -- muss sie gestellt werden.
    """
    from starlette.requests import Request

    return Request({
        "type": "http", "method": "GET", "path": "/api/karten/suchen",
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 1234),
    })


@pytest.mark.asyncio
async def test_alchemy_rebalanced_cards_are_excluded():
    """Regression: die Suche nach "Orcish Bowmaster" lieferte ZWEI Treffer --
    die echte Karte und "A-Orcish Bowmasters". Letztere ist die Alchemy-Fassung:
    es gibt sie nur digital in MTG Arena, sie ist in keinem Papierformat legal
    und hat keinen Marktpreis. In einer Sammel- und Deckbau-App für Papierkarten
    ist sie ein irreführendes Duplikat."""
    from routers.cards import karten_suchen_liste

    gestellte_fragen = []

    async def fake_request(client, method, url, **kw):
        frage = urllib.parse.unquote_plus(url.split("q=", 1)[1].split("&")[0])
        gestellte_fragen.append(frage)
        return FakeResponse(200, {"data": [{"name": "Orcish Bowmasters", "type_line": "Creature"}]})

    with patch("routers.cards.scryfall_request", fake_request), \
         patch("routers.cards.scryfall_cache", _LeererCache()):
        ergebnis = await karten_suchen_liste(
            q="Orcish Bowmaster", request=_anfrage(), limit=5,
            current_user="tester")

    assert [k["name"] for k in ergebnis["karten"]] == ["Orcish Bowmasters"]
    assert gestellte_fragen, "Es wurde gar nicht gesucht"
    assert all("-is:rebalanced" in f for f in gestellte_fragen), gestellte_fragen
