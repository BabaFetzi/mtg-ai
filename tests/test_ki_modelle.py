"""Welche Funktion auf welchem Modell läuft.

Vorher stand diese Entscheidung verstreut in acht Dateien: jede Aufrufstelle
importierte `model` oder `model_lite` und entschied damit nebenbei mit. Die
Frage "welche Funktion kostet uns das teure Modell?" liess sich nur durch
Quelltextlesen beantworten -- und die Antwort war an einer Stelle sogar falsch
(routers/vision.py prüfte `model`, benutzte aber das kleine).

Jetzt steht die Zuordnung in services/ki_modelle.py. Diese Tests halten fest,
was daran verlässlich sein muss.
"""

import pytest

from services import ki_modelle
from services.ki_modelle import GROSS, KLEIN, stufe_fuer, uebersicht


@pytest.fixture(autouse=True)
def ohne_ueberschreibungen(monkeypatch):
    for funktion in list(ki_modelle.ZUORDNUNG) + ["irgendwas"]:
        monkeypatch.delenv(f"GEMINI_STUFE_{funktion.upper()}", raising=False)


# ----------------------------------------------------------------------
# Die Zuordnung selbst
# ----------------------------------------------------------------------

def test_nur_die_deck_analyse_braucht_die_teure_stufe():
    """Das ist die Aussage, auf der die Kostenrechnung beruht. Rutscht hier
    eine zweite Funktion auf die grosse Stufe, verdoppelt sich ein Posten --
    lautlos."""
    gross = [f for f, stufe in uebersicht().items() if stufe == GROSS]

    assert gross == ["deck_analyse"]


def test_die_vision_funktionen_laufen_auf_der_guenstigen_stufe():
    """Vision ist mit 432 Aufrufen je Nutzer und Monat der grösste Posten
    nach dem Text. Auf der teuren Stufe wäre es der grösste überhaupt."""
    for funktion in ("vision_erkennung", "vision_rat", "karte_erkennen"):
        assert stufe_fuer(funktion) == KLEIN, funktion


def test_jede_stufe_ist_eine_bekannte_stufe():
    for funktion, stufe in ki_modelle.ZUORDNUNG.items():
        assert stufe in ki_modelle.STUFEN, f"{funktion}: {stufe!r}"


# ----------------------------------------------------------------------
# Vollständigkeit
# ----------------------------------------------------------------------

def test_jede_aufgerufene_funktion_steht_in_der_tabelle():
    """Der eigentliche Zweck der Tabelle: dass sie vollständig ist.

    Gesucht wird nach jedem `feature="..."`, das im Code an Gemini übergeben
    wird. Wer eine neue KI-Funktion einbaut und den Eintrag vergisst, bekommt
    hier einen roten Test statt einer stillen Standardwahl.
    """
    import pathlib
    import re

    gefunden = set()
    for pfad in list(pathlib.Path("routers").glob("*.py")) + \
            list(pathlib.Path("services").glob("*.py")):
        text = pfad.read_text(encoding="utf-8")
        # feature="judge"  bzw.  ..., "kartenname_auswahl", None  in to_thread
        gefunden.update(re.findall(r'feature\s*=\s*"([a-z_]+)"', text))
        gefunden.update(re.findall(r'modell_fuer\("([a-z_]+)"\)', text))

    # "unbekannt" ist der Standardwert der Signatur, keine echte Funktion.
    gefunden.discard("unbekannt")

    fehlend = sorted(gefunden - set(ki_modelle.ZUORDNUNG))
    assert not fehlend, (
        f"Diese Funktionen rufen Gemini auf, stehen aber nicht in "
        f"services/ki_modelle.ZUORDNUNG: {fehlend}")


def test_unbekannte_funktion_faellt_auf_die_guenstige_stufe(caplog):
    """Eine vergessene Funktion soll auffallen, aber nichts kosten."""
    import logging

    with caplog.at_level(logging.WARNING):
        assert stufe_fuer("gibt_es_nicht") == KLEIN

    assert "gibt_es_nicht" in caplog.text


# ----------------------------------------------------------------------
# Umstellen ohne Codeänderung
# ----------------------------------------------------------------------

def test_umgebungsvariable_schlaegt_die_tabelle(monkeypatch):
    """Damit lässt sich eine einzelne Funktion umstellen und danach messen,
    ohne irgendetwas anderes anzufassen."""
    monkeypatch.setenv("GEMINI_STUFE_DECK_ANALYSE", "klein")

    assert stufe_fuer("deck_analyse") == KLEIN


def test_unsinniger_wert_aendert_nichts(monkeypatch, caplog):
    """Ein Tippfehler in der .env darf keine Funktion umschalten -- weder
    still noch überhaupt."""
    import logging

    monkeypatch.setenv("GEMINI_STUFE_DECK_ANALYSE", "riesig")

    with caplog.at_level(logging.ERROR):
        assert stufe_fuer("deck_analyse") == GROSS

    assert "GEMINI_STUFE_DECK_ANALYSE" in caplog.text


def test_leere_variable_aendert_nichts(monkeypatch):
    """Eine leere Zeile in der .env heisst "nicht gesetzt" -- wie überall."""
    monkeypatch.setenv("GEMINI_STUFE_DECK_ANALYSE", "")

    assert stufe_fuer("deck_analyse") == GROSS


# ----------------------------------------------------------------------
# Der Weg zum wirklichen Modell
# ----------------------------------------------------------------------

def test_modell_fuer_liefert_die_passende_stufe(monkeypatch):
    from services import ai_service

    monkeypatch.setattr(ai_service, "model", "GROSSES-MODELL", raising=False)
    monkeypatch.setattr(ai_service, "model_lite", "KLEINES-MODELL", raising=False)

    assert ai_service.modell_fuer("deck_analyse") == "GROSSES-MODELL"
    assert ai_service.modell_fuer("judge") == "KLEINES-MODELL"
    assert ai_service.modell_fuer("vision_erkennung") == "KLEINES-MODELL"


def test_ohne_ki_gibt_es_kein_modell(monkeypatch):
    """Ohne Schlüssel muss die Anwendung weiterlaufen -- die Aufrufstellen
    prüfen auf None."""
    from services import ai_service

    monkeypatch.setattr(ai_service, "model", None, raising=False)
    monkeypatch.setattr(ai_service, "model_lite", None, raising=False)

    assert ai_service.modell_fuer("deck_analyse") is None
    assert ai_service.modell_fuer("judge") is None
