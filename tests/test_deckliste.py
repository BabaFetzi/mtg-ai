"""Zeilen einer Deckliste ändern -- Hinzufügen, Entfernen, Auflage wechseln.

Diese Funktionen schreiben in das Deck des Nutzers. Ein Fehler hier ist kein
Anzeigefehler, sondern Datenverlust: eine zerschossene Zeile ist weg.
"""

import pytest

from services.deckliste import (
    auflage_setzen,
    ist_strukturzeile,
    karte_entfernen,
    karte_hinzufuegen,
    zeile_lesen,
)


# ----------------------------------------------------------------------
# Struktur erkennen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile", [
    "", "   ", "# Kommentar", "// Sideboard", "Kreaturen:", "Sideboard", "Deck", "COMMANDER",
])
def test_strukturzeilen(zeile):
    assert ist_strukturzeile(zeile)
    assert zeile_lesen(zeile) is None


@pytest.mark.parametrize("zeile", ["4 Lightning Bolt", "Sol Ring", "1x Sol Ring (LTC) 1"])
def test_kartenzeilen(zeile):
    assert not ist_strukturzeile(zeile)
    assert zeile_lesen(zeile) is not None


def test_zeile_ohne_anzahl_zaehlt_als_eins():
    assert zeile_lesen("Sol Ring")["anzahl"] == 1


# ----------------------------------------------------------------------
# Hinzufügen
# ----------------------------------------------------------------------
def test_vorhandene_karte_wird_hochgezaehlt():
    assert karte_hinzufuegen("4x Lightning Bolt", "Lightning Bolt") == "5x Lightning Bolt"


def test_neue_karte_kommt_ans_ende():
    assert karte_hinzufuegen("4x Lightning Bolt", "Sol Ring") == "4x Lightning Bolt\n1x Sol Ring"


def test_erste_karte_in_leerem_deck():
    assert karte_hinzufuegen("", "Sol Ring") == "1x Sol Ring"
    assert karte_hinzufuegen("\n\n", "Sol Ring") == "1x Sol Ring"


def test_mit_auflage_hinzugefuegt():
    assert karte_hinzufuegen("", "Lightning Bolt", "2xm", "123") == "1x Lightning Bolt (2XM) 123"


def test_gleiche_auflage_wird_hochgezaehlt():
    ergebnis = karte_hinzufuegen("2x Lightning Bolt (2XM) 123", "Lightning Bolt", "2xm", "123")
    assert ergebnis == "3x Lightning Bolt (2XM) 123"


def test_andere_auflage_wird_eine_eigene_zeile():
    """Der Kern von "welche Version habe ich".

    Wer ausdrücklich eine andere Auflage wählt, will genau die im Deck haben --
    nicht die vorhandene stillschweigend hochgezählt bekommen.
    """
    ergebnis = karte_hinzufuegen("2x Lightning Bolt (2XM) 123", "Lightning Bolt", "m10", "146")
    assert ergebnis == "2x Lightning Bolt (2XM) 123\n1x Lightning Bolt (M10) 146"


def test_ohne_auflage_zaehlt_die_vorhandene_hoch():
    """Aus der Kartensuche kommt oft nur ein Name.

    Dann ist "mach eine zweite Zeile ohne Auflage auf" die schlechtere Antwort:
    der Nutzer hat keine Auflage gewählt, also meint er die, die schon dasteht.
    """
    ergebnis = karte_hinzufuegen("2x Lightning Bolt (2XM) 123", "Lightning Bolt")
    assert ergebnis == "3x Lightning Bolt (2XM) 123"


def test_struktur_bleibt_erhalten():
    liste = "# Mein Deck\n\n4x Lightning Bolt\n\nSideboard\n2x Abrade"
    assert karte_hinzufuegen(liste, "Abrade") == (
        "# Mein Deck\n\n4x Lightning Bolt\n\nSideboard\n3x Abrade")


def test_ueberschrift_wird_nie_zur_karte():
    """"Sideboard" ist eine Überschrift, auch wenn jemand danach sucht."""
    liste = "4x Lightning Bolt\nSideboard\n2x Abrade"
    assert karte_hinzufuegen(liste, "Sideboard") == (
        "4x Lightning Bolt\nSideboard\n2x Abrade\n1x Sideboard")


def test_zeile_ohne_anzahl_bekommt_eine():
    assert karte_hinzufuegen("Sol Ring", "Sol Ring") == "2x Sol Ring"


# ----------------------------------------------------------------------
# Entfernen
# ----------------------------------------------------------------------
def test_entfernen_zaehlt_herunter():
    assert karte_entfernen("4x Lightning Bolt", "Lightning Bolt") == ("3x Lightning Bolt", True)


def test_letztes_exemplar_entfernt_die_zeile():
    assert karte_entfernen("4x Sol Ring\n1x Lightning Bolt", "Lightning Bolt") == (
        "4x Sol Ring", True)


def test_nicht_vorhandene_karte_meldet_sich():
    liste = "4x Lightning Bolt"
    assert karte_entfernen(liste, "Sol Ring") == (liste, False)


def test_entfernen_trifft_die_gewaehlte_auflage():
    liste = "2x Lightning Bolt (2XM) 123\n2x Lightning Bolt (M10) 146"
    assert karte_entfernen(liste, "Lightning Bolt", "m10", "146") == (
        "2x Lightning Bolt (2XM) 123\n1x Lightning Bolt (M10) 146", True)


def test_entfernen_ohne_auflage_nimmt_die_erste():
    liste = "2x Lightning Bolt (2XM) 123\n2x Lightning Bolt (M10) 146"
    assert karte_entfernen(liste, "Lightning Bolt") == (
        "1x Lightning Bolt (2XM) 123\n2x Lightning Bolt (M10) 146", True)


# ----------------------------------------------------------------------
# Auflage wechseln
# ----------------------------------------------------------------------
def test_auflage_wechseln():
    assert auflage_setzen("4x Lightning Bolt", "Lightning Bolt", None, None, "2xm", "123") == (
        "4x Lightning Bolt (2XM) 123", True)


def test_auflage_wechseln_ersetzt_die_alte():
    assert auflage_setzen("4x Lightning Bolt (M10) 146", "Lightning Bolt",
                          "m10", "146", "2xm", "123") == ("4x Lightning Bolt (2XM) 123", True)


def test_auflage_abwaehlen():
    """Zurück auf "egal welche Auflage" muss möglich sein."""
    assert auflage_setzen("4x Lightning Bolt (2XM) 123", "Lightning Bolt",
                          "2xm", "123", None, None) == ("4x Lightning Bolt", True)


def test_gleiche_auflagen_werden_zusammengelegt():
    """Zwei Zeilen mit derselben Auflage wären keine Information, sondern ein
    Fehler -- beim nächsten Bearbeiten würde nur eine davon gefunden."""
    liste = "4x Lightning Bolt (2XM) 123\n2x Lightning Bolt (M10) 146"
    assert auflage_setzen(liste, "Lightning Bolt", "m10", "146", "2xm", "123") == (
        "6x Lightning Bolt (2XM) 123", True)


def test_auflage_wechseln_bei_unbekannter_karte():
    liste = "4x Lightning Bolt"
    assert auflage_setzen(liste, "Sol Ring", None, None, "2xm", "123") == (liste, False)


def test_auflage_wechseln_laesst_andere_karten_in_ruhe():
    liste = "# Deck\n4x Lightning Bolt\n1x Sol Ring\n\nSideboard\n2x Abrade"
    neu, gefunden = auflage_setzen(liste, "Sol Ring", None, None, "ltc", "1")
    assert gefunden
    assert neu == "# Deck\n4x Lightning Bolt\n1x Sol Ring (LTC) 1\n\nSideboard\n2x Abrade"


# ----------------------------------------------------------------------
# Rundlauf mit dem Parser
# ----------------------------------------------------------------------
def test_geschriebene_zeilen_versteht_der_parser_wieder():
    """Die Eigenschaft, an der die ganze Speicherung hängt.

    Was hier in die Liste geschrieben wird, muss parse_decklist beim nächsten
    Laden als dieselbe Karte in derselben Auflage wiedererkennen -- sonst
    verschwindet die Auswahl des Nutzers beim Speichern.
    """
    from services.scryfall import parse_decklist

    liste = ""
    liste = karte_hinzufuegen(liste, "Lightning Bolt", "2xm", "123")
    liste = karte_hinzufuegen(liste, "Lightning Bolt", "2xm", "123")
    liste = karte_hinzufuegen(liste, "Lightning Bolt", "m10", "146")
    liste = karte_hinzufuegen(liste, "Sol Ring")

    assert parse_decklist(liste) == [
        {"count": 2, "name": "Lightning Bolt", "sideboard": False,
         "set": "2xm", "sammlernummer": "123"},
        {"count": 1, "name": "Lightning Bolt", "sideboard": False,
         "set": "m10", "sammlernummer": "146"},
        {"count": 1, "name": "Sol Ring", "sideboard": False,
         "set": None, "sammlernummer": None},
    ]
