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

from unittest.mock import AsyncMock, patch

import pytest

import services.multilingual_search as ml
from routers.cards import _namensschluessel, _fallback_lang_search

# Die KI-Stufe braucht seit der Kostenabsicherung einen angemeldeten Nutzer und
# bucht auf dessen Monatskontingent. Diese Tests prüfen die SUCHLOGIK, nicht die
# Abrechnung -- das Kontingent wird deshalb hier als vorhanden angenommen.
# Dass ohne Anmeldung gar nichts passiert, prüft tests/test_ki_kosten_schutz.py.
NUTZER = "suchtester"


@pytest.fixture(autouse=True)
def kontingent_vorhanden():
    with patch("services.usage_limiter.check_and_increment_search_ai",
               new=AsyncMock(return_value=True)):
        yield


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
# Übersetzung mit Auswahl aus ECHTEN Kartennamen
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def cache():
    fake = FakeCache()
    with patch.object(ml, "scryfall_cache", fake):
        yield fake


def _scryfall(exakt=None, fuzzy=None, suche=None):
    """Baut ein Scryfall-Double aus drei Zuordnungen: Name -> Ergebnis."""
    exakt, fuzzy, suche = exakt or {}, fuzzy or {}, suche or {}

    async def fake_request(client, method, url, **kw):
        import urllib.parse as up
        frage = up.unquote_plus(url.split("?", 1)[1] if "?" in url else "")
        if "/cards/named" in url:
            tabelle = exakt if frage.startswith("exact=") else fuzzy
            name = frage.split("=", 1)[1]
            treffer = tabelle.get(name)
            return FakeResponse(200, {"name": treffer}) if treffer else FakeResponse(404)
        if "/cards/search" in url:
            # "name:goblins -is:rebalanced" -> "goblins"
            wort = frage.split("name:", 1)[1].split("&")[0].split()[0]
            namen = suche.get(wort, [])
            return FakeResponse(200, {
                "total_cards": len(namen),
                "data": [{"name": n} for n in namen],
            })
        return FakeResponse(404)

    return fake_request


async def _waehlt(ziel):
    async def waehlen(begriff, auswahl):
        return ziel if ziel in auswahl else None
    return waehlen


@pytest.mark.asyncio
async def test_exact_proposal_still_needs_confirmation():
    """Ein exakter Vorschlag beweist nur, dass die Karte EXISTIERT -- nicht,
    dass es die richtige ist. Er kommt in die Auswahl wie jeder andere."""
    async def kandidaten(begriff):
        return ["Lightning Bolt"]

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Lightning Bolt")), \
         patch.object(ml, "scryfall_request", _scryfall(exakt={"Lightning Bolt": "Lightning Bolt"})):
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Blitzschlag")

    assert karte["name"] == "Lightning Bolt"


@pytest.mark.asyncio
async def test_real_but_wrong_card_proposal_is_not_taken_blindly():
    """DER gemeldete Fehler in seiner zweiten Ausprägung: das Modell schlug
    "Stoneforge Mystic" für "Steinstimmen-Goblins" vor. Weil das eine echt
    existierende Karte ist, wurde sie als "exakter Vorschlag" sofort
    übernommen -- die gesamte Auswahllogik wurde übersprungen."""
    async def kandidaten(begriff):
        return ["Stoneforge Mystic", "Stonevoice Goblins"]

    scryfall = _scryfall(
        exakt={"Stoneforge Mystic": "Stoneforge Mystic",
               "Stony-Voiced Goblins": "Stony-Voiced Goblins"},
        suche={"goblins": ["Stony-Voiced Goblins", "Goblin Shrine"],
               "mystic": ["Stoneforge Mystic", "Mystic Snake"]},
    )
    gezeigt = {}

    async def waehlt(begriff, auswahl):
        gezeigt["auswahl"] = auswahl
        return "Stony-Voiced Goblins"

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", waehlt), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Steinstimmen-Goblins")

    assert karte["name"] == "Stony-Voiced Goblins"
    assert "Stoneforge Mystic" in gezeigt["auswahl"], \
        "Der Vorschlag darf Kandidat sein -- aber eben nur Kandidat"


@pytest.mark.asyncio
async def test_words_of_the_original_query_are_searched_too():
    """Kreaturentypen und Eigennamen sind über Sprachen hinweg oft fast gleich.
    "Steinstimmen-Goblins" enthält "Goblins" -- damit wird die richtige Karte
    gefunden, ganz unabhängig davon, was das Modell vorschlägt."""
    async def kandidaten(begriff):
        return ["Completely Unrelated Guess"]

    scryfall = _scryfall(
        suche={"goblins": ["Stony-Voiced Goblins"]},
        exakt={"Stony-Voiced Goblins": "Stony-Voiced Goblins"},
    )

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Stony-Voiced Goblins")), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Steinstimmen-Goblins")

    assert karte["name"] == "Stony-Voiced Goblins"


@pytest.mark.asyncio
async def test_wrong_card_from_fuzzy_drift_is_rejected():
    """DER gemeldete Fehler: die Suche nach "Steinstimmen-Goblins" lieferte
    "Stoneforge Mystic". Ursache war Scryfalls grosszügige Fuzzy-Suche, die auf
    Wortanfängen matcht. Ein Fuzzy-Treffer, der dem Vorschlag nicht wirklich
    ähnelt, darf nicht mehr durchgehen."""
    assert ml._passt_klar_zusammen("Stonevoice Goblins", "Stoneforge Mystic") is False
    assert ml._passt_klar_zusammen("Stonespeaker Goblins", "Stonespeaker Crystal") is False
    assert ml._passt_klar_zusammen("Goblin Warrior", "Goblin Soldier") is False
    # Der knappste Fall: sieht sehr ähnlich aus (0.83), ist aber eine andere
    # Karte -- genau der Treffer, der im Deck landete.
    assert ml._passt_klar_zusammen("Stone Mystic", "Stoneforge Mystic") is False
    # Echte Entsprechungen müssen weiterhin durchkommen.
    assert ml._passt_klar_zusammen("Stone-Voiced Goblins", "Stony-Voiced Goblins") is True
    assert ml._passt_klar_zusammen("Lightning Bolt", "Lightning Bolt") is True


@pytest.mark.asyncio
async def test_real_card_is_found_via_word_search():
    """Vollständiger Ablauf des gemeldeten Falls: kein exakter Treffer, Fuzzy
    driftet weg -- die richtige Karte kommt über die Wortsuche und wird vom
    Modell aus echten Namen ausgewählt."""
    async def kandidaten(begriff):
        return ["Stonevoice Goblins"]

    scryfall = _scryfall(
        fuzzy={"Stonevoice Goblins": "Stoneforge Mystic"},   # der alte Fehltreffer
        suche={"goblins": ["Stony-Voiced Goblins", "Scarwood Goblins", "Goblin Shrine"]},
        exakt={"Stony-Voiced Goblins": "Stony-Voiced Goblins"},
    )

    vorgelegt = {}

    async def waehlt(begriff, auswahl):
        vorgelegt["auswahl"] = auswahl
        return "Stony-Voiced Goblins"

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", waehlt), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Steinstimmen-Goblins")

    assert karte["name"] == "Stony-Voiced Goblins"
    assert "Stoneforge Mystic" not in vorgelegt["auswahl"], \
        "Der Fehltreffer darf gar nicht erst zur Auswahl stehen"


@pytest.mark.asyncio
async def test_model_answer_outside_the_list_is_rejected():
    """Das Modell kann nichts erfinden: eine Antwort, die nicht wörtlich in der
    vorgelegten Liste steht, wird verworfen."""
    auswahl = ["Stony-Voiced Goblins", "Scarwood Goblins"]

    class FakeAntwort:
        text = "Goblin des Steins"

    class FakeModell:
        def generate_content(self, *a, **kw):
            return FakeAntwort()

    with patch("services.ai_service.model_lite", FakeModell()):
        assert await ml._modell_waehlt_aus_echten_namen("Steinstimmen-Goblins", auswahl) is None


@pytest.mark.asyncio
async def test_model_may_answer_none():
    class FakeAntwort:
        text = "KEINE"

    class FakeModell:
        def generate_content(self, *a, **kw):
            return FakeAntwort()

    with patch("services.ai_service.model_lite", FakeModell()):
        assert await ml._modell_waehlt_aus_echten_namen("Irgendwas", ["Sol Ring"]) is None


@pytest.mark.asyncio
async def test_hallucinated_card_yields_nothing():
    """Erfindet das Modell eine Karte, existiert dazu nichts -- und es darf
    NICHTS ausgeliefert werden."""
    async def kandidaten(begriff):
        return ["Totally Made Up Card"]

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", _scryfall()):
        assert await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Irgendein Fantasiename") is None


@pytest.mark.asyncio
async def test_result_is_cached_so_model_runs_once(cache):
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Fearsome Goblin Duo"]

    scryfall = _scryfall(exakt={"Fearsome Goblin Duo": "Fearsome Goblin Duo"})
    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Fearsome Goblin Duo")), \
         patch.object(ml, "scryfall_request", scryfall):
        await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")
        await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")

    assert aufrufe["n"] == 1, "Dieselbe Eingabe darf nur EINEN Modellaufruf kosten"


@pytest.mark.asyncio
async def test_negative_result_is_cached_too(cache):
    """Auch ein erfolgloser Begriff darf das Modell nicht wiederholt kosten."""
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Nichts Passendes"]

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "scryfall_request", _scryfall()):
        await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Unauffindbarer Kartenname")
        await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Unauffindbarer Kartenname")

    assert aufrufe["n"] == 1


@pytest.mark.asyncio
async def test_negative_cache_expires_so_a_card_is_not_lost_for_a_day(cache):
    """Regression: der Fehlschlag wurde 24 h gemerkt. Lief der Server beim
    ersten Versuch ohne API-Schlüssel, blieb die Karte danach einen ganzen Tag
    unauffindbar -- obwohl längst alles korrekt konfiguriert war."""
    aufrufe = {"n": 0}

    async def kandidaten(begriff):
        aufrufe["n"] += 1
        return ["Fearsome Goblin Pair"]

    gefunden = {"ja": False}

    async def scryfall(client, method, url, **kw):
        if gefunden["ja"] and "exact=" in url:
            return FakeResponse(200, {"name": "Fearsome Goblin Pair"})
        return FakeResponse(404)

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Fearsome Goblin Pair")), \
         patch.object(ml, "scryfall_request", scryfall):
        assert await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo") is None

        for eintrag in cache.daten.values():
            eintrag["zeit"] -= ml.NEGATIV_CACHE_SEKUNDEN + 1

        gefunden["ja"] = True
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")

    assert aufrufe["n"] == 2, "Nach Ablauf muss erneut gefragt werden"
    assert karte["name"] == "Fearsome Goblin Pair"


@pytest.mark.asyncio
async def test_missing_model_is_not_remembered_as_a_failure(cache):
    """Fehlt das Sprachmodell (z.B. kein GEMINI_API_KEY), ist das ein
    technischer Ausfall -- kein Beweis, dass es die Karte nicht gibt. Er darf
    den späteren, korrekt konfigurierten Versuch nicht blockieren."""
    async def kein_modell(begriff):
        return []

    with patch.object(ml, "_frage_modell_nach_englischen_namen", kein_modell):
        assert await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo") is None

    assert cache.daten == {}, "Ein technischer Ausfall darf nichts zementieren"

    async def kandidaten(begriff):
        return ["Fearsome Goblin Pair"]

    scryfall = _scryfall(exakt={"Fearsome Goblin Pair": "Fearsome Goblin Pair"})
    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Fearsome Goblin Pair")), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")

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
            assert await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff=unsinn) is None

    assert aufrufe["n"] == 0


@pytest.mark.asyncio
async def test_unspecific_word_search_is_skipped():
    """Ein Wort, das auf hunderte Karten passt, ergibt keine sinnvolle Auswahl
    -- daraus darf nichts abgeleitet werden."""
    async def scryfall(client, method, url, **kw):
        if "/cards/search" in url:
            return FakeResponse(200, {"total_cards": 5000, "data": [{"name": "Sol Ring"}]})
        return FakeResponse(404)

    with patch.object(ml, "scryfall_request", scryfall):
        assert await ml._echte_namen_zu(None, "Dragon Something") == []


@pytest.mark.asyncio
async def test_can_be_disabled():
    with patch.object(ml, "UEBERSETZUNGSSUCHE_AKTIV", False):
        assert await ml.finde_karte_sprachunabhaengig(None, benutzername=NUTZER, begriff="Blitzschlag") is None


# ======================================================================
# Das dauerhafte Gedaechtnis
# ======================================================================
# Eine einmal gegen Scryfall bestaetigte Zuordnung ist ein Fakt und verfaellt
# nicht. Vorher lag sie nur im Kartencache mit 24 Stunden Verfallszeit --
# danach wurde dieselbe Uebersetzung erneut bei Gemini gekauft. Jeden Tag,
# und von jedem Nutzer einzeln.

@pytest.mark.asyncio
async def test_bestaetigte_zuordnung_wird_dauerhaft_gemerkt(
        leeres_kartennamen_gedaechtnis):
    async def kandidaten(begriff):
        return ["Fearsome Goblin Pair"]

    scryfall = _scryfall(exakt={"Fearsome Goblin Pair": "Fearsome Goblin Pair"})
    with patch.object(ml, "_frage_modell_nach_englischen_namen", kandidaten), \
         patch.object(ml, "_modell_waehlt_aus_echten_namen", await _waehlt("Fearsome Goblin Pair")), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(
            None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")

    assert karte["name"] == "Fearsome Goblin Pair"
    assert leeres_kartennamen_gedaechtnis["furchterregendes goblin-duo"]["name"] \
        == "Fearsome Goblin Pair"


@pytest.mark.asyncio
async def test_ein_gemerkter_name_kostet_keinen_ki_aufruf(
        leeres_kartennamen_gedaechtnis, cache):
    """Der eigentliche Zweck. Der Cache ist leer, das Kontingent ungenutzt --
    trotzdem darf das Modell nicht mehr gefragt werden."""
    leeres_kartennamen_gedaechtnis["furchterregendes goblin-duo"] = {
        "name": "Fearsome Goblin Pair", "quelle": "ki_bestaetigt", "treffer": 0}

    gefragt = []

    async def darf_nicht_passieren(begriff):
        gefragt.append(begriff)
        return ["irgendwas"]

    scryfall = _scryfall(exakt={"Fearsome Goblin Pair": "Fearsome Goblin Pair"})
    with patch.object(ml, "_frage_modell_nach_englischen_namen", darf_nicht_passieren), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(
            None, benutzername=NUTZER, begriff="Furchterregendes Goblin-Duo")

    assert karte["name"] == "Fearsome Goblin Pair"
    assert gefragt == [], "Das Gedaechtnis haette den Modellaufruf sparen muessen"


@pytest.mark.asyncio
async def test_das_gedaechtnis_gilt_auch_ohne_kontingent(
        leeres_kartennamen_gedaechtnis):
    """Ein gemerkter Name muss auch dann noch funktionieren, wenn das
    Monatskontingent aufgebraucht ist -- es kostet ja nichts mehr."""
    leeres_kartennamen_gedaechtnis["blitzschlag"] = {
        "name": "Lightning Bolt", "quelle": "ki_bestaetigt", "treffer": 0}

    async def kein_kontingent(benutzername):
        return False

    scryfall = _scryfall(exakt={"Lightning Bolt": "Lightning Bolt"})
    with patch("services.usage_limiter.check_and_increment_search_ai", kein_kontingent), \
         patch.object(ml, "scryfall_request", scryfall):
        karte = await ml.finde_karte_sprachunabhaengig(
            None, benutzername=NUTZER, begriff="Blitzschlag")

    assert karte["name"] == "Lightning Bolt"
