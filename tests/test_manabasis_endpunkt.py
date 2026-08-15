"""tests/test_manabasis_endpunkt.py -- /api/deck/manabasis über die echte Route.

Prüft das Zusammenspiel: Deckliste zerlegen, Kartendaten holen, Sideboard
ausklammern und das Ergebnis so ausliefern, wie die Oberfläche es erwartet.
"""

import pytest
from fastapi.testclient import TestClient

import main
import routers.decks as decks_router

KARTEN = {
    "goblin chainwhirler": {
        "name": "Goblin Chainwhirler", "mana_cost": "{R}{R}{R}", "cmc": 3.0,
        "type": "Creature — Goblin Warrior", "oracle_text": "", "produced_mana": [],
    },
    "mountain": {
        "name": "Mountain", "mana_cost": "", "cmc": 0.0,
        "type": "Basic Land — Mountain", "oracle_text": "", "produced_mana": ["R"],
    },
    "island": {
        "name": "Island", "mana_cost": "", "cmc": 0.0,
        "type": "Basic Land — Island", "oracle_text": "", "produced_mana": ["U"],
    },
    "negate": {
        "name": "Negate", "mana_cost": "{1}{U}", "cmc": 2.0,
        "type": "Instant", "oracle_text": "", "produced_mana": [],
    },
}


@pytest.fixture
def klient(monkeypatch):
    async def falsche_daten(namen):
        return {n.lower().strip(): KARTEN[n.lower().strip()]
                for n in namen if n.lower().strip() in KARTEN}

    monkeypatch.setattr(decks_router, "fetch_card_details_cached", falsche_daten)
    main.app.dependency_overrides[decks_router.get_current_user] = lambda: "tester"
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def test_zu_wenig_rote_quellen_wird_gemeldet(klient):
    deck = "4 Goblin Chainwhirler\n12 Mountain\n44 Island"
    antwort = klient.post("/api/deck/manabasis", json={"deck_liste": deck})

    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["deckgroesse"] == 60
    assert daten["laender_gesamt"] == 56

    rot = next(f for f in daten["farben"] if f["farbe"] == "R")
    assert rot["farbname"] == "Rot"
    assert rot["laender"] == 12
    assert rot["haertester_bedarf"] == 3
    assert rot["reicht"] is False
    assert rot["fehlende_laender"] > 0


def test_sideboard_zaehlt_nicht_zur_starthand(klient):
    """Sideboard-Karten liegen zu Spielbeginn nicht im Deck. Zählte man sie
    mit, wäre jede Wahrscheinlichkeit falsch."""
    deck = "4 Negate\n56 Island\nSideboard\n15 Mountain"
    daten = klient.post("/api/deck/manabasis", json={"deck_liste": deck}).json()

    assert daten["deckgroesse"] == 60
    assert all(f["farbe"] != "R" for f in daten["farben"])


def test_unbekannte_karten_werden_benannt(klient):
    deck = "4 Karte Die Es Nicht Gibt\n56 Mountain"
    daten = klient.post("/api/deck/manabasis", json={"deck_liste": deck}).json()

    assert daten["nicht_gefunden"] == ["Karte Die Es Nicht Gibt"]
    # Die unbekannten Karten fehlen in der Deckgrösse -- genau deshalb werden
    # sie mitgeliefert.
    assert daten["deckgroesse"] == 56


def test_leere_liste_stuerzt_nicht_ab(klient):
    daten = klient.post("/api/deck/manabasis", json={"deck_liste": ""}).json()
    assert daten["deckgroesse"] == 0
    assert daten["farben"] == []


def test_ohne_anmeldung_kein_zugriff():
    with TestClient(main.app) as c:
        antwort = c.post("/api/deck/manabasis", json={"deck_liste": "60 Mountain"})
    assert antwort.status_code in (401, 403)
