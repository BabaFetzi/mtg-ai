"""Die Hochrechnung in werkzeuge/ki_kosten.py.

Das Werkzeug misst echte Tokenzahlen -- dafür braucht es einen gültigen
GEMINI_API_KEY, den es hier nicht gibt. Was sich aber ohne Schlüssel prüfen
lässt, ist die Rechnung selbst, und genau die erzeugt am Ende die Zahl, nach
der eine Geschäftsentscheidung getroffen wird.

Ein Rechenfehler hier wäre besonders heimtückisch: das Werkzeug liefe
durch, gäbe einen plausibel aussehenden Betrag aus, und niemand hätte einen
Anlass, ihn anzuzweifeln.
"""

import pytest

from werkzeuge.ki_kosten import _bericht

GROSS = "gemini-2.5-flash"
KLEIN = "gemini-2.5-flash-lite"


def zeile(funktion, ein, aus, modell=KLEIN, erfolg=1):
    return {"funktion": funktion, "modell": modell, "erfolg": erfolg,
            "prompt_tokens": ein, "antwort_tokens": aus,
            "gesamt_tokens": (ein or 0) + (aus or 0), "fehler": None}


# Eine erfundene, aber vollständige Messung. Die Zahlen sind bewusst rund,
# damit die Hochrechnung von Hand nachvollziehbar bleibt.
MESSUNG = [
    zeile("judge", 1_000, 500),
    zeile("deck_analyse", 4_000, 1_000, modell=GROSS),   # grosses Modell
    zeile("deck_roast", 2_000, 400),
    zeile("kartenname_uebersetzung", 300, 100),
    zeile("kartenname_auswahl", 200, 50),
    zeile("vision_erkennung", 800, 200),
    zeile("vision_rat", 300, 400),
]


@pytest.fixture
def preise(monkeypatch):
    """Glatte Preise je Modell: gross 1.00/2.00, klein 0.10/0.20."""
    monkeypatch.delenv("GEMINI_PRICE_INPUT_PER_MTOK", raising=False)
    monkeypatch.delenv("GEMINI_PRICE_OUTPUT_PER_MTOK", raising=False)
    # Semikolon trennt die Eintraege -- ein Komma waere das Dezimalzeichen.
    monkeypatch.setenv("GEMINI_PREISE",
                       f"{GROSS}:1.00/2.00; {KLEIN}:0.10/0.20")


def test_jedes_modell_wird_mit_seinem_eigenen_preis_gerechnet(preise, capsys):
    """Der Grund für den Umbau: die Deck-Analyse laeuft auf dem grossen
    Modell, alles andere auf dem kleinen. Laut Preisliste liegt dazwischen
    Faktor 20 und mehr -- ein Einheitspreis waere grob falsch."""
    _bericht(MESSUNG, abo=None, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    # 300 x deck_analyse auf dem GROSSEN Modell:
    #   1.200.000 ein * 1.00 + 300.000 aus * 2.00 = 1.20 + 0.60 = 1.80
    assert "1.8000" in ausgabe
    # 432 x vision_erkennung auf dem KLEINEN Modell:
    #   345.600 ein * 0.10 + 86.400 aus * 0.20 = 0.03456 + 0.01728 = 0.0518
    assert "0.0518" in ausgabe


def test_die_summe_stimmt(preise, capsys):
    """Von Hand nachgerechnet -- die Zahl, an der die Entscheidung hängt."""
    _bericht(MESSUNG, abo=None, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    # Text   300 x (4000/1000) gross: 1.200.000*1.00 + 300.000*2.00 = 1.80000
    # Bild   432 x  (800/200)  klein:   345.600*0.10 +  86.400*0.20 = 0.05184
    # Rat    432 x  (300/400)  klein:   129.600*0.10 + 172.800*0.20 = 0.04752
    # Suche  100 x  (500/150)  klein:    50.000*0.10 +  15.000*0.20 = 0.00800
    #                                                          Summe = 1.90736
    assert "1.9074" in ausgabe


def test_teuerster_textaufruf_wird_in_geld_gemessen_nicht_in_tokens(preise, capsys):
    """Ein Aufruf mit WENIGER Tokens kann mehr kosten, wenn er auf dem
    teuren Modell laeuft. Wer nach Tokens sortiert, setzt den falschen an."""
    messung = [
        # Viele Tokens, aber billiges Modell.
        zeile("deck_roast", 50_000, 10_000, modell=KLEIN),
        # Wenige Tokens, teures Modell -- und trotzdem teurer:
        #   50.000*0.10 + 10.000*0.20 = 0.007
        #   20.000*1.00 + 5.000*2.00  = 0.030
        zeile("deck_analyse", 20_000, 5_000, modell=GROSS),
    ]

    _bericht(messung, abo=None, waehrung="CHF")

    assert "deck_analyse, teuerster" in capsys.readouterr().out


def test_unbekanntes_modell_wird_gemeldet_statt_geraten(capsys, monkeypatch):
    """Der Fall, der bei Grana wirklich auftrat: in der Abrechnung stand ein
    Modell, das auf der Preisseite gar nicht vorkam. Es einfach mit dem Preis
    eines anderen zu rechnen waere die gefaehrlichste aller Varianten."""
    monkeypatch.delenv("GEMINI_PRICE_INPUT_PER_MTOK", raising=False)
    monkeypatch.delenv("GEMINI_PRICE_OUTPUT_PER_MTOK", raising=False)
    monkeypatch.setenv("GEMINI_PREISE", f"{KLEIN}:0.10/0.20")

    _bericht([zeile("deck_analyse", 4_000, 1_000, modell="gemini-3.7-flash"),
              zeile("vision_erkennung", 800, 200)],
             abo=3.90, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert "Preis fehlt" in ausgabe
    assert "gemini-3.7-flash" in ausgabe
    assert "der echte Betrag ist also HÖHER" in ausgabe


def test_kurs_rechnet_die_preise_um(preise, capsys):
    """Googles Liste ist in USD, die Abrechnung laeuft in CHF."""
    _bericht(MESSUNG, abo=None, waehrung="CHF", kurs=0.5)
    ausgabe = capsys.readouterr().out

    # Halber Kurs -> halbe Summe: 1.90736 / 2 = 0.95368
    assert "0.9537" in ausgabe
    assert "Umrechnungsfaktor 0.5" in ausgabe


def test_alter_einheitspreis_gilt_weiter(capsys, monkeypatch):
    """Wer nur ein Modell benutzt, soll nichts umstellen muessen."""
    monkeypatch.delenv("GEMINI_PREISE", raising=False)
    monkeypatch.setenv("GEMINI_PRICE_INPUT_PER_MTOK", "1.00")
    monkeypatch.setenv("GEMINI_PRICE_OUTPUT_PER_MTOK", "2.00")

    # Vollstaendige Messung: hier geht es um den Preis, nicht um die
    # Vollstaendigkeitspruefung -- die haette sonst schon vorher abgebrochen.
    _bericht(MESSUNG, abo=None, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert "Preis fehlt" not in ausgabe
    assert "kostet dich im schlimmsten Fall" in ausgabe


def test_negative_marge_wird_als_fehler_gemeldet(preise, capsys):
    """Der eigentliche Zweck: wenn ein Nutzer mehr kostet als er zahlt, darf
    das Werkzeug nicht mit Erfolg enden."""
    kode = _bericht(MESSUNG, abo=1.00, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert kode == 2
    assert "drauf" in ausgabe.lower()


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
    monkeypatch.delenv("GEMINI_PREISE", raising=False)
    monkeypatch.delenv("GEMINI_PRICE_INPUT_PER_MTOK", raising=False)
    monkeypatch.delenv("GEMINI_PRICE_OUTPUT_PER_MTOK", raising=False)

    kode = _bericht(MESSUNG, abo=3.90, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert kode == 0
    assert "Keine Preise hinterlegt" in ausgabe
    assert "kostet dich im schlimmsten Fall" not in ausgabe


# ----------------------------------------------------------------------
# Wenn das Ersatzmodell einspringt
# ----------------------------------------------------------------------
# Aufgetreten in einem echten Lauf: die Deck-Analyse bekam auf dem grossen
# Modell HTTP 503 ("high demand"), die Anwendung wiederholte den Aufruf
# automatisch auf dem kleinen -- und der Bericht rechnete danach die gesamten
# 300 Textaufrufe mit dem GUENSTIGEN Preis.
#
# Die Zahl sah beruhigend aus und war zu niedrig. Genau die Richtung, in die
# man sich bei einem Abo-Geschaeft nicht irren darf.

def test_ersatzmodell_wird_gemeldet(preise, capsys):
    messung = [
        # So sieht es im Protokoll aus: ein Fehlschlag auf dem grossen Modell...
        dict(zeile("deck_analyse", None, None, modell=GROSS, erfolg=0),
             fehler="503 UNAVAILABLE: This model is currently experiencing high demand"),
        # ...und direkt danach der geglueckte Versuch auf dem kleinen.
        zeile("deck_analyse", 2_521, 958, modell=KLEIN),
        zeile("vision_erkennung", 800, 200),
    ]

    _bericht(messung, abo=3.90, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert "ERSATZMODELL" in ausgabe
    assert GROSS in ausgabe                      # was angefragt war
    assert "HÖHER" in ausgabe                    # in welche Richtung es abweicht


def test_ohne_ersatz_kein_hinweis(preise, capsys):
    """Die Gegenprobe -- eine saubere Messung darf nicht gewarnt werden."""
    _bericht(MESSUNG, abo=20.00, waehrung="CHF")

    assert "ERSATZMODELL" not in capsys.readouterr().out


def test_gescheitert_auf_demselben_modell_ist_kein_ersatz(preise, capsys):
    """Ein Fehlversuch und ein geglueckter Versuch auf DEMSELBEN Modell heisst
    nur, dass es beim zweiten Mal geklappt hat -- gerechnet wird richtig."""
    messung = [
        dict(zeile("deck_analyse", None, None, modell=GROSS, erfolg=0),
             fehler="503 UNAVAILABLE"),
        zeile("deck_analyse", 2_521, 958, modell=GROSS),
    ]

    _bericht(messung, abo=20.00, waehrung="CHF")

    assert "ERSATZMODELL" not in capsys.readouterr().out


# ----------------------------------------------------------------------
# Eine fehlende Messung ist kein Nullposten
# ----------------------------------------------------------------------
# Aufgetreten im zweiten echten Lauf: Deck-Analyse, Deck-Roast und Kartensuche
# kamen aus dem Cache (dieselben Testdaten wie beim ersten Lauf), also wurde
# Gemini gar nicht gefragt und es standen nur noch 3 statt 9 Aufrufe im
# Protokoll. Alle Endpunkte meldeten trotzdem HTTP 200.
#
# Der Bericht setzte daraufhin fuer den teuersten Textaufruf den Judge an
# (866 Tokens auf dem guenstigen Modell statt 2.521 auf dem teuren), rechnete
# die Kartensuche mit 0 und meldete "0.72 CHF, Marge 81 Prozent" -- mit
# Rueckgabewert 0, also als sauberes Ergebnis.

def test_fehlende_messung_verhindert_ein_ergebnis(preise, capsys):
    nur_teilweise = [
        zeile("judge", 866, 174),
        zeile("vision_erkennung", 1_181, 318),
        zeile("vision_rat", 245, 164),
        # deck_analyse, deck_roast und die Kartensuche fehlen -- aus dem Cache.
    ]

    kode = _bericht(nur_teilweise, abo=3.90, waehrung="CHF", kurs=0.79)
    ausgabe = capsys.readouterr().out

    assert kode == 3, "eine unvollstaendige Messung darf kein Erfolg sein"
    assert "KEIN ERGEBNIS" in ausgabe
    assert "Deck-Analyse" in ausgabe
    assert "Deck-Roast" in ausgabe
    assert "Kartensuche" in ausgabe
    # Und vor allem: keine Marge, die nach einem Ergebnis aussieht.
    assert "Marge" not in ausgabe


def test_vollstaendige_messung_liefert_weiterhin_ein_ergebnis(preise, capsys):
    """Die Gegenprobe -- MESSUNG deckt alle erwarteten Funktionen ab."""
    kode = _bericht(MESSUNG, abo=20.00, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert kode == 0
    assert "KEIN ERGEBNIS" not in ausgabe
    assert "Marge" in ausgabe


def test_null_tokens_zaehlen_nicht_als_messung(preise, capsys):
    """Die Kartensuche stand mit 0 Eingabe / 0 Ausgabe in der Tabelle und ging
    trotzdem als gemessen durch -- ein Aufruf ohne Tokens ist keine Messung."""
    messung = [dict(z) for z in MESSUNG]
    for z in messung:
        if z["funktion"] == "kartenname_uebersetzung":
            z["prompt_tokens"] = z["antwort_tokens"] = 0
        if z["funktion"] == "kartenname_auswahl":
            z["prompt_tokens"] = z["antwort_tokens"] = 0

    kode = _bericht(messung, abo=20.00, waehrung="CHF")

    assert kode == 3
    assert "Kartensuche" in capsys.readouterr().out


# ----------------------------------------------------------------------
# Nach einer geglueckten Wiederholung
# ----------------------------------------------------------------------
# gemini-3.7-flash meldet regelmaessig 503 "high demand". Das Werkzeug
# wiederholt den Schritt deshalb. Danach liegen ZWEI Messungen vor: die billige
# vom Ersatzmodell und die vom Hauptmodell.
#
# Die Namen lassen sich dabei nicht vergleichen -- der gescheiterte Aufruf
# protokolliert den Alias ("gemini-flash-latest"), der gelungene das Modell,
# das wirklich geantwortet hat ("gemini-3.7-flash"). Dasselbe Modell, voellig
# verschiedene Zeichenketten.

ALIAS = "gemini-flash-latest"


def test_geglueckte_wiederholung_beendet_die_warnung(preise, capsys):
    messung = [
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0),
             fehler="503 UNAVAILABLE: high demand"),
        zeile("deck_analyse", 2_521, 1_247, modell=KLEIN),   # Ersatz
        zeile("deck_analyse", 2_521, 1_247, modell=GROSS),   # Wiederholung geglueckt
        zeile("judge", 866, 144),
        zeile("deck_roast", 2_306, 396),
        zeile("kartenname_uebersetzung", 171, 7),
        zeile("vision_erkennung", 1_181, 318),
        zeile("vision_rat", 245, 231),
    ]

    _bericht(messung, abo=20.00, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert "ERSATZMODELL" not in ausgabe


def test_wiederholung_wird_auch_gerechnet(preise, capsys):
    """Nicht nur die Warnung verschwindet -- die Hochrechnung muss die TEURE
    Messung nehmen. Der erste gelungene Aufruf ist der billige vom Ersatz;
    wer den nimmt, hat die Wiederholung umsonst bezahlt."""
    messung = [
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0),
             fehler="503"),
        zeile("deck_analyse", 1_000, 1_000, modell=KLEIN),   # billig, zuerst
        zeile("deck_analyse", 1_000, 1_000, modell=GROSS),   # teuer, danach
        zeile("judge", 100, 100),
        zeile("deck_roast", 100, 100),
        zeile("kartenname_uebersetzung", 100, 100),
        zeile("vision_erkennung", 100, 100),
        zeile("vision_rat", 100, 100),
    ]

    _bericht(messung, abo=20.00, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    # 300x auf dem GROSSEN Modell: 300.000 * 1.00 + 300.000 * 2.00 = 0.90
    # Auf dem kleinen waeren es 300.000 * 0.10 + 300.000 * 0.20 = 0.09
    assert "0.9000" in ausgabe
    assert "deck_analyse" in ausgabe


def test_gescheiterte_wiederholung_warnt_weiter(preise, capsys):
    """Bleibt das Hauptmodell ueberlastet, muss die Warnung stehenbleiben."""
    messung = [
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0),
             fehler="503"),
        zeile("deck_analyse", 2_521, 1_247, modell=KLEIN),
        zeile("judge", 866, 144),
        zeile("deck_roast", 2_306, 396),
        zeile("kartenname_uebersetzung", 171, 7),
        zeile("vision_erkennung", 1_181, 318),
        zeile("vision_rat", 245, 231),
    ]

    _bericht(messung, abo=20.00, waehrung="CHF")
    ausgabe = capsys.readouterr().out

    assert "ERSATZMODELL" in ausgabe
    assert ALIAS in ausgabe


def test_dauerhaft_ausgefallenes_hauptmodell_raet_zum_festlegen(preise, capsys):
    """Drei Fehlversuche hintereinander sind kein "gerade viel los" mehr.

    Warten hilft dann nicht. Und schlimmer als die Kostenfrage: im laufenden
    Betrieb zahlt JEDER Aufruf erst einen vergeblichen Versuch, bevor das
    Ersatzmodell antwortet -- das kostet die Nutzer Wartezeit bei jeder
    einzelnen Deck-Analyse.
    """
    messung = [
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0), fehler="503"),
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0), fehler="503"),
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0), fehler="503"),
        zeile("deck_analyse", 2_521, 1_237, modell=KLEIN),
        zeile("judge", 866, 205),
        zeile("deck_roast", 2_306, 420),
        zeile("kartenname_uebersetzung", 171, 7),
        zeile("vision_erkennung", 1_181, 312),
        zeile("vision_rat", 239, 230),
    ]

    _bericht(messung, abo=3.90, waehrung="CHF", kurs=0.79)
    ausgabe = capsys.readouterr().out

    assert "3x ausgefallen" in ausgabe
    assert "kein vorübergehender Engpass" in ausgabe
    assert "Wartezeit" in ausgabe
    assert f"GEMINI_MODEL={KLEIN}" in ausgabe


def test_ein_einzelner_ausfall_raet_zum_abwarten(preise, capsys):
    """Einmal 503 ist wirklich nur Auslastung -- da waere "festnageln" der
    falsche Rat."""
    messung = [
        dict(zeile("deck_analyse", None, None, modell=ALIAS, erfolg=0), fehler="503"),
        zeile("deck_analyse", 2_521, 1_237, modell=KLEIN),
        zeile("judge", 866, 205),
        zeile("deck_roast", 2_306, 420),
        zeile("kartenname_uebersetzung", 171, 7),
        zeile("vision_erkennung", 1_181, 312),
        zeile("vision_rat", 239, 230),
    ]

    _bericht(messung, abo=3.90, waehrung="CHF", kurs=0.79)
    ausgabe = capsys.readouterr().out

    assert "1x ausgefallen" in ausgabe
    assert "noch einmal laufen" in ausgabe
    assert "GEMINI_MODEL=" not in ausgabe
