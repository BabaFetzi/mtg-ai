"""
tests/test_rules_corpus.py – Offizielle Regeln als Wissensquelle für den Judge

Massnahme 6: Der Judge kannte bisher keinerlei Regeltext (das App-Regelbuch sind
14 fest einprogrammierte Regeln im Frontend, ohne KI-Zugriff). Jetzt werden die
passenden Stellen der Comprehensive Rules nachgeschlagen.

Alle Tests laufen gegen einen kleinen, eingebetteten Regelausschnitt -- kein
Netzwerk, keine Abhängigkeit von der grossen Originaldatei.
"""

from unittest.mock import patch

import pytest

import services.rules_corpus as rc


REGELTEXT = """Magic: The Gathering Comprehensive Rules

103.5. Each player draws a number of cards equal to their starting hand size, which is normally seven. A player who is dissatisfied with their initial hand may take a mulligan.

608.2b. If the spell or ability specifies targets, it checks whether the targets are still legal. A target that's no longer in the zone it was in when it was targeted is illegal.

702.2b. A creature with toughness greater than 0 that's been dealt damage by a source with deathtouch since the last state-based actions check is destroyed as a state-based action.

702.12a. Trample is a static ability that modifies the rules for assigning an attacking creature's combat damage.

704.5f. If a creature has toughness 0 or less, it's put into its owner's graveyard as a state-based action.

100.1
"""


@pytest.fixture(autouse=True)
def korpus():
    """Lädt den Testkorpus, ohne Netzwerk oder Datei zu berühren."""
    rc._reset_for_tests()
    with patch.object(rc, "_lade_rohtext", lambda: REGELTEXT):
        yield
    rc._reset_for_tests()


# ----------------------------------------------------------------------
# Parsen
# ----------------------------------------------------------------------
def test_parse_extracts_numbered_rules():
    regeln = rc.parse_rules(REGELTEXT)
    nummern = [n for n, _ in regeln]
    assert "702.2b" in nummern
    assert "608.2b" in nummern


def test_parse_skips_table_of_contents_entries():
    """Nackte Nummern ohne Fliesstext (Inhaltsverzeichnis) sind keine Regeln."""
    assert "100.1" not in [n for n, _ in rc.parse_rules(REGELTEXT)]


def test_parse_handles_empty_input():
    assert rc.parse_rules("") == []


# ----------------------------------------------------------------------
# Suche
# ----------------------------------------------------------------------
def test_direct_rule_number_is_returned_first():
    treffer = rc.suche_regeln("Was sagt Regel 704.5f?", limit=3)
    assert treffer[0][0] == "704.5f"


def test_german_question_finds_english_rule():
    """Kernproblem: Die Fragen sind deutsch, die Regeln englisch."""
    treffer = rc.suche_regeln("Wie funktioniert Todesberührung?", limit=3)
    assert "702.2b" in [n for n, _ in treffer]


def test_german_trample_term_is_translated():
    treffer = rc.suche_regeln("Was macht Trampelschaden genau?", limit=3)
    assert "702.12a" in [n for n, _ in treffer]


def test_oracle_text_terms_bridge_to_rules():
    """Der englische Kartentext liefert die Fachbegriffe für die Regelsuche."""
    treffer = rc.suche_regeln(
        "Wie wirkt diese Karte?",
        extra_terms=["Target creature gains deathtouch until end of turn."],
        limit=3,
    )
    assert "702.2b" in [n for n, _ in treffer]


def test_most_specific_rule_ranks_first():
    """BM25 muss die Definition vor beiläufigen Erwähnungen einordnen."""
    treffer = rc.suche_regeln("targets are no longer legal spell", limit=3)
    assert treffer[0][0] == "608.2b"


def test_search_returns_nothing_for_unrelated_question():
    assert rc.suche_regeln("Wie ist das Wetter in Zürich?", limit=3) == []


def test_limit_is_respected():
    assert len(rc.suche_regeln("creature damage state-based graveyard", limit=2)) <= 2


def test_empty_question_returns_nothing():
    assert rc.suche_regeln("", limit=3) == []


# ----------------------------------------------------------------------
# Robustheit
# ----------------------------------------------------------------------
def test_missing_corpus_degrades_silently():
    """Ist der Regeltext nicht verfügbar, antwortet der Judge weiterhin."""
    rc._reset_for_tests()
    with patch.object(rc, "_lade_rohtext", lambda: None):
        assert rc.suche_regeln("Wie funktioniert Todesberührung?") == []


def test_corpus_is_loaded_only_once():
    """Ein fehlgeschlagener Download darf nicht bei jeder Frage wiederholt werden."""
    rc._reset_for_tests()
    aufrufe = {"n": 0}

    def zaehlend():
        aufrufe["n"] += 1
        return None

    with patch.object(rc, "_lade_rohtext", zaehlend):
        rc.suche_regeln("Frage eins")
        rc.suche_regeln("Frage zwei")

    assert aufrufe["n"] == 1


def test_can_be_disabled_by_configuration():
    with patch.object(rc, "RULES_ENABLED", False):
        assert rc.suche_regeln("Wie funktioniert Todesberührung?") == []


# ----------------------------------------------------------------------
# Einbindung in den Judge
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_judge_prompt_cites_official_rules():
    from routers.ai import _build_judge_prompt

    async def keine_karten(names):
        return {}

    with patch("routers.ai.fetch_card_details_cached", keine_karten):
        prompt = await _build_judge_prompt("Wie funktioniert Todesberührung?")

    assert "OFFIZIELLE REGELN" in prompt
    assert "702.2b" in prompt
    assert "Regelnummer in deiner Antwort" in prompt


@pytest.mark.asyncio
async def test_judge_prompt_survives_rules_failure():
    from routers.ai import _build_judge_prompt

    async def keine_karten(names):
        return {}

    with patch("routers.ai.fetch_card_details_cached", keine_karten), \
         patch("routers.ai.suche_regeln", side_effect=RuntimeError("kaputt")):
        prompt = await _build_judge_prompt("Wie funktioniert Todesberührung?")

    assert "FRAGE:" in prompt
    assert "Erfinde NIEMALS" in prompt
