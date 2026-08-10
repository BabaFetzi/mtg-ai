"""
tests/test_card_query_tool.py – Kartensuche als Werkzeug für das Modell (Massnahme 5)

Das Modell soll strukturierte Kartenfragen ("blaue Kreaturen unter 3 Mana mit
Fliegend, Standard-legal") über eine echte Abfrage beantworten statt zu raten.
Grana braucht dafür keine eigene Kartendatenbank -- Scryfall ist bereits exakt
abfragbar.

Zusätzlich abgesichert: Der Judge-Aufruf blockiert den Event-Loop nicht mehr und
fällt bei einem Werkzeugfehler sauber auf den Aufruf ohne Werkzeug zurück.
"""

from unittest.mock import patch

import pytest

import services.card_query_tool as tool


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


@pytest.fixture(autouse=True)
def cache():
    fake = FakeCache()
    with patch.object(tool, "scryfall_cache", fake), \
         patch.object(tool, "_MIN_INTERVAL", 0.0):
        yield fake


TREFFER = {
    "total_cards": 2,
    "data": [
        {"name": "Faerie Mastermind", "type_line": "Creature — Faerie Rogue",
         "mana_cost": "{1}{U}", "oracle_text": "Flash\nFlying"},
        {"name": "Spectral Sailor", "type_line": "Creature — Spirit Pirate",
         "mana_cost": "{U}", "oracle_text": "Flash\nFlying"},
    ],
}


# ----------------------------------------------------------------------
# Abfrage
# ----------------------------------------------------------------------
def test_search_returns_compact_card_facts():
    with patch.object(tool.httpx, "get", return_value=FakeResponse(200, TREFFER)):
        ergebnis = tool.karten_suchen("c:u t:creature cmc<=3 o:flying")

    assert ergebnis["anzahl"] == 2
    assert [k["name"] for k in ergebnis["karten"]] == ["Faerie Mastermind", "Spectral Sailor"]
    assert ergebnis["karten"][0]["manakosten"] == "{1}{U}"
    assert "Flying" in ergebnis["karten"][0]["regeltext"]


def test_query_is_passed_through_to_scryfall():
    """Die Scryfall-Syntax muss unverändert ankommen -- sie ist der Kern des Werkzeugs."""
    with patch.object(tool.httpx, "get", return_value=FakeResponse(200, TREFFER)) as get:
        tool.karten_suchen("t:land f:commander")

    assert get.call_args.kwargs["params"]["q"] == "t:land f:commander"


def test_no_results_is_not_an_error():
    """Scryfall meldet 'keine Treffer' mit HTTP 404 -- das ist kein Fehlerfall."""
    with patch.object(tool.httpx, "get", return_value=FakeResponse(404)):
        ergebnis = tool.karten_suchen("t:creature o:'does not exist'")

    assert ergebnis["anzahl"] == 0
    assert ergebnis["karten"] == []
    assert "Keine Karte" in ergebnis["hinweis"]


def test_invalid_syntax_yields_hint_not_exception():
    with patch.object(tool.httpx, "get", return_value=FakeResponse(400)):
        ergebnis = tool.karten_suchen("cmc<<<3")
    assert ergebnis["karten"] == []
    assert "fehlgeschlagen" in ergebnis["hinweis"]


def test_network_failure_degrades_gracefully():
    with patch.object(tool.httpx, "get", side_effect=RuntimeError("offline")):
        ergebnis = tool.karten_suchen("t:creature")
    assert ergebnis["karten"] == []
    assert "nicht erreichbar" in ergebnis["hinweis"]


def test_empty_query_is_rejected_without_network():
    with patch.object(tool.httpx, "get", side_effect=AssertionError("darf nicht aufgerufen werden")):
        ergebnis = tool.karten_suchen("   ")
    assert ergebnis["anzahl"] == 0


def test_results_are_capped_and_flagged():
    viele = {"total_cards": 500, "data": [
        {"name": f"Karte {i}", "type_line": "Creature", "mana_cost": "{G}", "oracle_text": "x"}
        for i in range(50)
    ]}
    with patch.object(tool.httpx, "get", return_value=FakeResponse(200, viele)):
        ergebnis = tool.karten_suchen("t:creature")

    assert len(ergebnis["karten"]) == tool.MAX_ERGEBNISSE
    assert "500" in ergebnis["hinweis"]


def test_repeated_query_is_served_from_cache():
    with patch.object(tool.httpx, "get", return_value=FakeResponse(200, TREFFER)) as get:
        tool.karten_suchen("t:creature")
        tool.karten_suchen("t:creature")
    assert get.call_count == 1


def test_double_faced_card_text_is_joined():
    dfc = {"total_cards": 1, "data": [{
        "name": "Delver of Secrets // Insectile Aberration",
        "type_line": "Creature — Human Wizard",
        "mana_cost": "{U}",
        "card_faces": [{"oracle_text": "Vorderseite"}, {"oracle_text": "Rückseite"}],
    }]}
    with patch.object(tool.httpx, "get", return_value=FakeResponse(200, dfc)):
        ergebnis = tool.karten_suchen("delver")
    assert "Vorderseite // Rückseite" in ergebnis["karten"][0]["regeltext"]


# ----------------------------------------------------------------------
# Einbindung in den Judge
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_judge_passes_tool_to_model():
    import routers.ai as ai

    class FakeModel:
        def __init__(self):
            self.kwargs = None

        def generate_content(self, prompt, **kwargs):
            self.kwargs = kwargs
            class R:
                text = "Antwort"
            return R()

    fake = FakeModel()
    with patch.object(ai, "model_lite", fake), patch.object(ai, "JUDGE_CARD_TOOL_ENABLED", True):
        antwort = await ai._judge_modell_aufrufen("Prompt", "tester")

    assert antwort == "Antwort"
    assert fake.kwargs["tools"] == [tool.karten_suchen]


@pytest.mark.asyncio
async def test_judge_falls_back_when_tool_call_fails():
    """Eine bezahlte, funktionierende Funktion darf durch das Werkzeug nie ausfallen."""
    import routers.ai as ai

    aufrufe = []

    class FakeModel:
        def generate_content(self, prompt, **kwargs):
            aufrufe.append("mit" if kwargs.get("tools") else "ohne")
            if kwargs.get("tools"):
                raise RuntimeError("Function-Calling nicht unterstützt")
            class R:
                text = "Antwort ohne Werkzeug"
            return R()

    with patch.object(ai, "model_lite", FakeModel()), patch.object(ai, "JUDGE_CARD_TOOL_ENABLED", True):
        antwort = await ai._judge_modell_aufrufen("Prompt", "tester")

    assert antwort == "Antwort ohne Werkzeug"
    assert aufrufe == ["mit", "ohne"]


@pytest.mark.asyncio
async def test_tool_can_be_disabled():
    import routers.ai as ai

    class FakeModel:
        def __init__(self):
            self.kwargs = None

        def generate_content(self, prompt, **kwargs):
            self.kwargs = kwargs
            class R:
                text = "Antwort"
            return R()

    fake = FakeModel()
    with patch.object(ai, "model_lite", fake), patch.object(ai, "JUDGE_CARD_TOOL_ENABLED", False):
        await ai._judge_modell_aufrufen("Prompt", "tester")

    assert "tools" not in fake.kwargs


@pytest.mark.asyncio
async def test_judge_model_call_does_not_block_the_event_loop():
    """Der synchrone Gemini-Aufruf muss in einem Thread laufen, sonst steht
    während einer Judge-Anfrage der ganze Server."""
    import asyncio
    import routers.ai as ai

    laeuft = {"parallel": False}

    class LangsamesModel:
        def generate_content(self, prompt, **kwargs):
            import time
            time.sleep(0.25)
            class R:
                text = "Antwort"
            return R()

    async def nebenher():
        # Läuft der Modellaufruf im Thread, kommt diese Aufgabe währenddessen dran.
        await asyncio.sleep(0.05)
        laeuft["parallel"] = True

    with patch.object(ai, "model_lite", LangsamesModel()), \
         patch.object(ai, "JUDGE_CARD_TOOL_ENABLED", False):
        await asyncio.gather(ai._judge_modell_aufrufen("Prompt", "tester"), nebenher())

    assert laeuft["parallel"] is True, "Der Event-Loop war während des Modellaufrufs blockiert"
