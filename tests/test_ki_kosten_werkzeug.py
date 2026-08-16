"""Die Hochrechnung in werkzeuge/ki_kosten.py.

Das Werkzeug misst echte Tokenzahlen -- dafür braucht es einen gültigen
GEMINI_API_KEY, den es hier nicht gibt. Was sich aber ohne Schlüssel prüfen
lässt, ist die Rechnung selbst, und genau die erzeugt am Ende die Zahl, nach
der eine Geschäftsentscheidung getroffen wird.

Ein Rechenfehler hier wäre besonders heimtückisch: das Werkzeug liefe
durch, gäbe einen plausibel aussehenden Betrag aus, und niemand hätte einen
Anlass, ihn anzuzweifeln.
"""

import os

import pytest

from werkzeuge.ki_kosten import _bericht, _kosten, _preise


def zeile(funktion, ein, aus, modell="gemini-3.7-flash", erfolg=1):
    return {"funktion": funktion, "modell": modell, "erfolg": erfolg,
            "prompt_tokens": ein, "antwort_tokens": aus,
            "gesamt_tokens": (ein or 0) + (aus or 0), "fehler": None}


# Eine erfundene, aber vollständige Messung. Die Zahlen sind bewusst rund,
# damit die Hochrechnung von Hand nachvollziehbar bleibt.
MESSUNG = [
    zeile("judge", 1_000, 500),
    zeile("deck_analyse", 4_000, 1_000),      # der teuerste Textaufruf
    zeile("deck_roast", 2_000, 400),
    zeile("kartenname_uebersetzung", 300, 100),
    zeile("kartenname_auswahl", 200, 50),
    zeile("vision_erkennung", 800, 200),
    zeile("vision_rat", 300, 400),
]


@pytest.fixture
def preise(monkeypatch):
    # Glatte Preise: 1 Mio. Eingabe-Tokens = 1.00, Ausgabe = 2.00.
    monkeypatch.setenv("GEMINI_PRICE_INPUT_PER_MTOK", "1.00")
    monkeypatch.setenv("GEMINI_PRICE_OUTPUT_PER_MTOK", "2.00")


def test_preise_werden_gelesen(preise):
    assert _preise() == (1.00, 2.00)


def test_komma_als_dezimaltrennzeichen(monkeypatch):
    monkeypatch.setenv("GEMINI_PRICE_INPUT_PER_MTOK", "0,30")
    monkeypatch.delenv("GEMINI_PRICE_OUTPUT_PER_MTOK", raising=False)
    # Wer den Preis aus einer deutschen Preisseite abschreibt, tippt ein Komma.
    assert _preise()[0] == 0.30


def test_kostenformel():
    # 2 Mio. Eingabe zu 1.00 + 1 Mio. Ausgabe zu 2.00 = 4.00
    assert _kosten(2_000_000, 1_000_000, 1.00, 2.00) == pytest.approx(4.00)


def test_ohne_preise_kein_betrag():
    """Ein geratener Preis wäre schlimmer als gar keiner."""
    assert _kosten(1_000_000, 1_000_000, None, None) is None


def test_hochrechnung_nimmt_den_teuersten_textaufruf(preise, capsys):
    """Das Text-Kontingent ist frei verteilbar. Wer mit dem Durchschnitt
    rechnet, weist eine Obergrenze aus, die keine ist."""
    _bericht(MESSUNG, abo=None, waehrung="CHF")

    ausgabe = capsys.readouterr().out
    # deck_analyse ist mit 5000 Tokens der teuerste -- er muss angesetzt werden.
    assert "deck_analyse" in ausgabe
    assert "300x Text" in ausgabe


def test_vision_und_suche_werden_nicht_doppelt_gezaehlt(preise, capsys):
    """Vision und Suche haben eigene Kontingente. Zählte man sie zusätzlich
    zum Text-Kontingent, stünden sie zweimal in der Summe."""
    _bericht(MESSUNG, abo=None, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    # Der teuerste Textposten darf keiner der Vision-/Suchaufrufe sein.
    assert "vision_erkennung, teuerster" not in ausgabe
    assert "kartenname" not in ausgabe.split("Hochrechnung")[1].split("Summe")[0] \
        or "Kartensuche" in ausgabe


def test_die_summe_stimmt(preise, capsys):
    """Von Hand nachgerechnet -- die Zahl, an der die Entscheidung hängt."""
    _bericht(MESSUNG, abo=None, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    # 300 x deck_analyse       -> 1.200.000 ein / 300.000 aus
    # 432 x vision_erkennung   ->   345.600 ein /  86.400 aus
    # 432 x vision_rat         ->   129.600 ein / 172.800 aus
    # 100 x Suche (2 Aufrufe)  ->    50.000 ein /  15.000 aus
    #                     Summe: 1.725.200 ein / 574.200 aus
    # Kosten: 1,7252 * 1.00 + 0,5742 * 2.00 = 2,8736
    assert "2.8736" in ausgabe or "2,8736" in ausgabe.replace(".", ",")


def test_negative_marge_wird_als_fehler_gemeldet(preise, capsys):
    """Der eigentliche Zweck: wenn ein Nutzer mehr kostet als er zahlt, darf
    das Werkzeug nicht mit Erfolg enden."""
    kode = _bericht(MESSUNG, abo=1.00, waehrung="CHF")

    ausgabe = capsys.readouterr().out
    assert kode == 2
    assert "drauf" in ausgabe.lower()
    # 2,8736 Kosten bei 1,00 Abo -> die Marge muss negativ ausgewiesen werden.
    assert "-1.87" in ausgabe


def test_ausreichende_marge_ist_kein_fehler(preise, capsys):
    kode = _bericht(MESSUNG, abo=20.00, waehrung="CHF")

    assert kode == 0
    assert "Marge" in capsys.readouterr().out


def test_ohne_erfolgreiche_messung_kein_ergebnis(preise, capsys):
    """Nur gescheiterte Aufrufe: dann gibt es nichts hochzurechnen, und das
    Werkzeug muss das sagen statt eine Null auszuweisen."""
    nur_fehler = [dict(zeile("judge", None, None, erfolg=0), fehler="API key not valid")]

    kode = _bericht(nur_fehler, abo=3.90, waehrung="CHF")

    assert kode == 1
    assert "Kein einziger Aufruf" in capsys.readouterr().out


def test_ohne_preise_wird_kein_betrag_behauptet(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_PRICE_INPUT_PER_MTOK", raising=False)
    monkeypatch.delenv("GEMINI_PRICE_OUTPUT_PER_MTOK", raising=False)

    kode = _bericht(MESSUNG, abo=3.90, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert kode == 0
    assert "Keine Preise hinterlegt" in ausgabe
    assert "kostet dich im schlimmsten Fall" not in ausgabe
