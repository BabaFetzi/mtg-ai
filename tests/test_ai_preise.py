"""Preise je Modell.

Ein Einheitspreis für alle Modelle war grob falsch: die Anwendung benutzt das
grosse Modell für die Deck-Analyse und das kleine für alles andere, und laut
Googles Preisliste liegen dazwischen Faktor 20 und mehr.

Der heikelste Fall steht ganz unten: ein Modell, für das gar kein Preis
hinterlegt ist. Genau das ist bei Grana aufgetreten -- in der Abrechnung stand
ein "Gemini 3.7 Flash", das auf der Preisseite gar nicht vorkam. Es
stillschweigend mit dem Preis eines anderen Modells zu rechnen wäre die
gefährlichste aller Varianten: die Zahl sähe plausibel aus und wäre falsch.
"""

import pytest

from services.ai_preise import ALLGEMEIN, kosten, preis_fuer, tabelle


@pytest.fixture(autouse=True)
def saubere_umgebung(monkeypatch):
    for name in ("GEMINI_PREISE", "GEMINI_PRICE_INPUT_PER_MTOK",
                 "GEMINI_PRICE_OUTPUT_PER_MTOK"):
        monkeypatch.delenv(name, raising=False)


def test_preise_je_modell(monkeypatch):
    monkeypatch.setenv(
        "GEMINI_PREISE",
        "gemini-2.5-flash:0.30/2.50; gemini-2.5-flash-lite:0.10/0.40")

    assert preis_fuer("gemini-2.5-flash") == (0.30, 2.50)
    assert preis_fuer("gemini-2.5-flash-lite") == (0.10, 0.40)


def test_grossschreibung_und_leerzeichen_stoeren_nicht(monkeypatch):
    monkeypatch.setenv("GEMINI_PREISE",
                       "  Gemini-2.5-Flash : 0.30/2.50 ;\n gemini-2.5-flash-lite:0.10/0.40")

    assert preis_fuer("gemini-2.5-FLASH") == (0.30, 2.50)
    assert preis_fuer("gemini-2.5-flash-lite") == (0.10, 0.40)


def test_komma_als_dezimaltrennzeichen(monkeypatch):
    """Wer den Preis von einer deutschen Seite abschreibt, tippt ein Komma.

    Deshalb trennt ein SEMIKOLON die Eintraege: mit Komma als Trennzeichen
    waere "0,30" in zwei kaputte Haelften zerfallen -- der Preis haette
    gefehlt, ohne dass die Summe erkennbar falsch ausgesehen haette.
    """
    monkeypatch.setenv("GEMINI_PREISE", "gemini-2.5-flash:0,30/2,50")

    assert preis_fuer("gemini-2.5-flash") == (0.30, 2.50)


def test_unbekanntes_modell_hat_keinen_preis(monkeypatch):
    monkeypatch.setenv("GEMINI_PREISE", "gemini-2.5-flash-lite:0.10/0.40")

    assert preis_fuer("gemini-3.7-flash") == (None, None)
    assert kosten(1_000_000, 1_000_000, "gemini-3.7-flash") is None


def test_none_heisst_unbekannt_nicht_kostenlos(monkeypatch):
    """Der wichtigste Unterschied. Wer None als 0 verbucht, weist einen zu
    niedrigen Betrag aus -- und das ist die Richtung, in die man sich bei
    einem Abo-Geschäft nicht irren darf."""
    assert kosten(5_000_000, 5_000_000, "irgendwas") is None


def test_kostenformel(monkeypatch):
    monkeypatch.setenv("GEMINI_PREISE", "m:1.00/2.00")

    # 2 Mio. Eingabe zu 1.00 + 1 Mio. Ausgabe zu 2.00 = 4.00
    assert kosten(2_000_000, 1_000_000, "m") == pytest.approx(4.00)


def test_alter_einheitspreis_gilt_als_auffangwert(monkeypatch):
    """Wer nur ein Modell benutzt, soll nichts umstellen müssen."""
    monkeypatch.setenv("GEMINI_PRICE_INPUT_PER_MTOK", "0.30")
    monkeypatch.setenv("GEMINI_PRICE_OUTPUT_PER_MTOK", "2.50")

    assert ALLGEMEIN in tabelle()
    assert preis_fuer("völlig-unbekanntes-modell") == (0.30, 2.50)


def test_eigener_eintrag_schlaegt_den_auffangwert(monkeypatch):
    monkeypatch.setenv("GEMINI_PRICE_INPUT_PER_MTOK", "9.00")
    monkeypatch.setenv("GEMINI_PRICE_OUTPUT_PER_MTOK", "9.00")
    monkeypatch.setenv("GEMINI_PREISE", "gemini-2.5-flash-lite:0.10/0.40")

    assert preis_fuer("gemini-2.5-flash-lite") == (0.10, 0.40)
    assert preis_fuer("etwas-anderes") == (9.00, 9.00)


def test_kaputte_eintraege_werden_uebersprungen(monkeypatch):
    """Ein Tippfehler in einem Eintrag darf nicht die ganze Tabelle
    unbrauchbar machen -- der Rest muss weiter gelten."""
    monkeypatch.setenv("GEMINI_PREISE",
                       "unsinn-ohne-preis;noch-was:kaputt;gemini-2.5-flash:0.30/2.50")

    assert preis_fuer("gemini-2.5-flash") == (0.30, 2.50)


def test_negative_preise_werden_verworfen(monkeypatch):
    monkeypatch.setenv("GEMINI_PREISE", "m:-1.00/2.00")

    assert preis_fuer("m") == (None, 2.00)


def test_preisaenderung_wirkt_ohne_neustart(monkeypatch):
    """Die Tabelle wird bei jedem Aufruf gelesen. Wuerde sie beim Import
    zwischengespeichert, muesste man fuer eine Preisanpassung neu starten."""
    monkeypatch.setenv("GEMINI_PREISE", "m:1.00/1.00")
    assert preis_fuer("m") == (1.00, 1.00)

    monkeypatch.setenv("GEMINI_PREISE", "m:2.00/2.00")
    assert preis_fuer("m") == (2.00, 2.00)
