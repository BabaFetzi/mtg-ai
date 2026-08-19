"""Auflagen in der Deckliste -- Lesen, Schreiben, Vergleichen.

Der Kern von "welche Version einer Karte steckt im Deck". Die Gegenprobe ist
hier wichtiger als der Normalfall: eine falsch erkannte Auflage zeigt ein
falsches Bild und einen falschen Preis, und beides sieht aus wie eine Tatsache.
"""

import pytest

from services.auflagen import (
    auflage_anhaengen,
    auflage_lesen,
    auflage_schluessel,
    besitz_schluessel,
    besitz_zu_auflage,
    gleiche_auflage,
    zeile_zerlegen,
)


# ----------------------------------------------------------------------
# Lesen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("eingabe,name,set_code,nummer", [
    ("Lightning Bolt (2XM) 123", "Lightning Bolt", "2xm", "123"),
    ("Lightning Bolt (2xm) 123", "Lightning Bolt", "2xm", "123"),
    ("Lightning Bolt [2XM] 123", "Lightning Bolt", "2xm", "123"),
    ("Lightning Bolt (2XM)", "Lightning Bolt", "2xm", None),
    ("Cavern of Souls (LCI) 269", "Cavern of Souls", "lci", "269"),
    # Fünf- und sechsstellige Set-Codes gibt es wirklich (PLIST, PW21).
    ("Sol Ring (PLIST) 42", "Sol Ring", "plist", "42"),
    # Sammlernummern mit Buchstaben und Sternchen.
    ("Brainstorm (MH2) 42a", "Brainstorm", "mh2", "42a"),
    ("Brainstorm (MH2) ★42", "Brainstorm", "mh2", "★42"),
    # Doppelseitige Karten behalten ihren Namen; die Vorderseite zieht erst
    # clean_card_name heraus.
    ("Fire // Ice (APC) 128", "Fire // Ice", "apc", "128"),
])
def test_auflage_wird_erkannt(eingabe, name, set_code, nummer):
    assert auflage_lesen(eingabe) == (name, set_code, nummer)


@pytest.mark.parametrize("eingabe", [
    "Lightning Bolt",
    "Snow-Covered Forest",
    # Klammerbemerkungen, die keine Set-Codes sind: zu lang.
    "Sol Ring (Commander)",
    "Sol Ring (Showcase)",
    "Sol Ring (Extended Art)",
    # Zu kurz für einen Set-Code.
    "Sol Ring (X)",
    # Eine Zeile ganz ohne Namen ist keine Kartenzeile.
    "(2XM) 123",
])
def test_ohne_auflage_bleibt_der_name_unveraendert(eingabe):
    name, set_code, nummer = auflage_lesen(eingabe)
    assert (set_code, nummer) == (None, None)
    assert name == eingabe.strip()


@pytest.mark.parametrize("eingabe,name,set_code,nummer", [
    ("Lightning Bolt (2XM) 123 *F*", "Lightning Bolt *F*", "2xm", "123"),
    ("Lightning Bolt (2XM) 123 foil", "Lightning Bolt foil", "2xm", "123"),
])
def test_foil_marke_verdeckt_die_auflage_nicht(eingabe, name, set_code, nummer):
    """Arena und MTGO hängen die Foil-Marke hinter die Sammlernummer.

    Ohne diese Behandlung ginge "*F*" als Sammlernummer durch -- die Auflage
    liesse sich danach bei Scryfall nicht mehr auflösen.
    """
    assert auflage_lesen(eingabe) == (name, set_code, nummer)


def test_leere_eingabe():
    assert auflage_lesen("") == ("", None, None)
    assert auflage_lesen(None) == ("", None, None)


# ----------------------------------------------------------------------
# Schreiben -- und zurücklesen
# ----------------------------------------------------------------------
def test_anhaengen_schreibt_die_standardschreibweise():
    assert auflage_anhaengen("Lightning Bolt", "2xm", "123") == "Lightning Bolt (2XM) 123"
    assert auflage_anhaengen("Lightning Bolt", "2xm") == "Lightning Bolt (2XM)"


def test_ohne_set_code_kommt_der_name_unveraendert_zurueck():
    """Eine Sammlernummer allein bezeichnet keine Auflage."""
    assert auflage_anhaengen("Lightning Bolt", None, "123") == "Lightning Bolt"
    assert auflage_anhaengen("Lightning Bolt", "", "123") == "Lightning Bolt"


@pytest.mark.parametrize("name,set_code,nummer", [
    ("Lightning Bolt", "2xm", "123"),
    ("Cavern of Souls", "lci", "269"),
    ("Sol Ring", "plist", None),
    ("Fire // Ice", "apc", "128"),
])
def test_geschrieben_und_wieder_gelesen_ergibt_dasselbe(name, set_code, nummer):
    """Der Rundlauf ist die Eigenschaft, an der die Speicherung hängt.

    Was das Programm in die Deckliste schreibt, muss es beim nächsten Laden
    wieder als dieselbe Auflage erkennen -- sonst wandert die Auswahl des
    Nutzers beim Speichern still verloren.
    """
    assert auflage_lesen(auflage_anhaengen(name, set_code, nummer)) == (name, set_code, nummer)


# ----------------------------------------------------------------------
# Vergleichen
# ----------------------------------------------------------------------
def test_gleiche_auflage_ignoriert_gross_und_kleinschreibung():
    assert gleiche_auflage("2XM", "123", "2xm", "123")


def test_fehlende_sammlernummer_entscheidet_der_set_code():
    assert gleiche_auflage("2xm", None, "2xm", "123")
    assert gleiche_auflage("2xm", "123", "2xm", None)


def test_verschiedene_auflagen_sind_verschieden():
    assert not gleiche_auflage("2xm", "123", "m10", "146")
    assert not gleiche_auflage("2xm", "123", "2xm", "124")


def test_ohne_auflage_gilt_nur_ohne_auflage():
    assert gleiche_auflage(None, None, None, None)
    assert not gleiche_auflage(None, None, "2xm", "123")


def test_schluessel():
    assert auflage_schluessel("2XM", "123") == "2xm/123"
    assert auflage_schluessel("2XM", None) == "2xm"
    assert auflage_schluessel(None, "123") is None


# ----------------------------------------------------------------------
# Besitz je Auflage
# ----------------------------------------------------------------------
def test_besitz_zaehlt_unter_beiden_schluesseln():
    besitz = besitz_schluessel([
        {"edition": "2XM", "sammlernummer": "123", "anzahl": 1},
        {"edition": "2xm", "sammlernummer": "123", "anzahl": 1},
        {"edition": "m10", "sammlernummer": "146", "anzahl": 1},
    ])
    assert besitz_zu_auflage(besitz, "2xm", "123") == 2
    assert besitz_zu_auflage(besitz, "m10", "146") == 1
    assert besitz_zu_auflage(besitz, "lea", "161") == 0


def test_sammlungseintrag_ohne_sammlernummer_markiert_trotzdem():
    """Ältere Sammlungseinträge haben keine Sammlernummer.

    Sie zählen dann für die ganze Edition -- sonst erschiene eine Auflage als
    nicht besessen, obwohl die Karte im Regal liegt.
    """
    besitz = besitz_schluessel([{"edition": "2xm", "sammlernummer": None, "anzahl": 3}])
    assert besitz_zu_auflage(besitz, "2xm", "123") == 3
    assert besitz_zu_auflage(besitz, "2xm", None) == 3


def test_besitz_ohne_edition_wird_uebergangen():
    assert besitz_schluessel([{"edition": None, "sammlernummer": "123", "anzahl": 1}]) == {}
    assert besitz_schluessel([]) == {}
    assert besitz_schluessel(None) == {}


def test_unlesbare_stueckzahl_zaehlt_als_eins():
    besitz = besitz_schluessel([{"edition": "2xm", "sammlernummer": "123", "anzahl": "viele"}])
    assert besitz_zu_auflage(besitz, "2xm", "123") == 1


# ----------------------------------------------------------------------
# Ganze Zeilen
# ----------------------------------------------------------------------
def test_zeile_zerlegen():
    assert zeile_zerlegen("4x Lightning Bolt (2XM) 123") == {
        "anzahl": 4, "name": "Lightning Bolt", "set": "2xm", "sammlernummer": "123"}
    assert zeile_zerlegen("4 Lightning Bolt") == {
        "anzahl": 4, "name": "Lightning Bolt", "set": None, "sammlernummer": None}


def test_zeile_ohne_stueckzahl():
    assert zeile_zerlegen("Lightning Bolt") is None
    assert zeile_zerlegen("") is None
