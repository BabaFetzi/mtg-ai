"""tests/test_manabasis.py -- Farbquellen gegen Farbbedarf.

Was einem Spieler auffällt, dem Programm bisher aber nicht: ein Deck mit
{R}{R}-Karten auf Zug 2 und zwölf Bergen zieht regelmässig die falsche Hand.
Die Prüfung rechnet das aus, statt es zu schätzen -- deshalb prüfen diese Tests
auch die Rechnung selbst gegen von Hand nachvollziehbare Werte.
"""

import pytest

from services.manabasis import (
    analysiere,
    erzeugte_farben,
    farbbedarf,
    gesehene_karten,
    noetige_quellen,
    wahrscheinlichkeit,
)


def karte(name, mana_cost="", typ="Creature — Human", cmc=None, produced=None, text=""):
    info = {
        "name": name,
        "mana_cost": mana_cost,
        "type": typ,
        "oracle_text": text,
        "cmc": len(mana_cost.split("}")) - 1 if cmc is None else cmc,
    }
    if produced is not None:
        info["produced_mana"] = produced
    return info


BERG = karte("Mountain", typ="Basic Land — Mountain", cmc=0, produced=["R"])
INSEL = karte("Island", typ="Basic Land — Island", cmc=0, produced=["U"])


# ----------------------------------------------------------------------
# Farbbedarf aus den Manakosten
# ----------------------------------------------------------------------
def test_zaehlt_farbige_symbole():
    assert farbbedarf("{1}{R}{R}") == {"R": 2}
    assert farbbedarf("{2}{W}{U}") == {"W": 1, "U": 1}


def test_generisches_mana_zaehlt_nicht():
    assert farbbedarf("{5}") == {}
    assert farbbedarf("") == {}


def test_hybrid_zaehlt_fuer_beide_farben():
    """{R/G} lässt sich mit Rot ODER Grün bezahlen -- der Bedarf an einer
    einzelnen Farbe steigt dadurch nicht."""
    assert farbbedarf("{R/G}") == {"R": 1, "G": 1}


# ----------------------------------------------------------------------
# Welche Karte erzeugt welche Farbe?
# ----------------------------------------------------------------------
def test_produced_mana_wird_bevorzugt():
    assert erzeugte_farben(BERG) == {"R"}


def test_ohne_produced_mana_wird_der_regeltext_gelesen():
    """Alte Cache-Einträge kennen das Feld nicht. Ohne diesen Rückfall würden
    ihre Länder stillschweigend als 'erzeugt kein Mana' gezählt."""
    alt = {"name": "Sulfur Falls", "type": "Land", "oracle_text": "{T}: Add {U} or {R}."}
    assert erzeugte_farben(alt) == {"U", "R"}


def test_beliebige_farbe_zaehlt_fuer_alle():
    quelle = {"name": "Birds of Paradise", "type": "Creature — Bird",
              "oracle_text": "{T}: Add one mana of any color."}
    assert erzeugte_farben(quelle) == {"W", "U", "B", "R", "G"}


def test_leeres_produced_mana_bedeutet_keine_quelle():
    assert erzeugte_farben(karte("Grizzly Bears", "{1}{G}", produced=[])) == set()


# ----------------------------------------------------------------------
# Die Rechnung selbst
# ----------------------------------------------------------------------
def test_wahrscheinlichkeit_von_hand_nachgerechnet():
    """Deck aus 2 Karten, 1 Quelle, 1 gezogene Karte -> genau 50 Prozent."""
    assert wahrscheinlichkeit(2, 1, 1, 1) == pytest.approx(0.5)


def test_alle_karten_gesehen_heisst_sicher():
    assert wahrscheinlichkeit(60, 20, 60, 2) == pytest.approx(1.0)


def test_zu_wenige_quellen_sind_unmoeglich():
    assert wahrscheinlichkeit(60, 1, 20, 2) == 0.0


def test_gesehene_karten_auf_dem_spiel():
    assert gesehene_karten(1) == 7
    assert gesehene_karten(3) == 9
    # Auf dem Zug zieht man eine Karte mehr.
    assert gesehene_karten(3, auf_dem_spiel=False) == 10


def test_noetige_quellen_fuer_ein_symbol_auf_zug_eins():
    """Von Hand nachrechenbar: mit 16 Quellen in 60 Karten liegt die Chance,
    unter den ersten sieben Karten mindestens eine zu haben, bei 90,1 Prozent;
    mit 15 nur bei 88,2.

    Die bekannten Manabasis-Tabellen nennen für denselben Fall 14 Quellen. Der
    Unterschied ist kein Rechenfehler, sondern eine andere Annahme: dort wird
    das Mulligan mitsimuliert (Hände ohne Land wirft man weg). Hier steht
    bewusst die nackte Ziehwahrscheinlichkeit ohne Mulligan -- eine Zahl, die
    sich nachprüfen lässt, statt einer abgeschriebenen."""
    assert wahrscheinlichkeit(60, 16, 7, 1) == pytest.approx(0.901, abs=0.001)
    assert wahrscheinlichkeit(60, 15, 7, 1) == pytest.approx(0.882, abs=0.001)
    assert noetige_quellen(60, gesehene_karten(1), 1) == 16


def test_doppelte_farbe_braucht_deutlich_mehr():
    einfach = noetige_quellen(60, gesehene_karten(2), 1)
    doppelt = noetige_quellen(60, gesehene_karten(2), 2)
    assert doppelt > einfach + 4


# ----------------------------------------------------------------------
# Gesamtanalyse
# ----------------------------------------------------------------------
def test_zu_wenige_quellen_werden_beanstandet():
    deck = [(4, karte("Goblin Chainwhirler", "{R}{R}{R}", cmc=3)), (12, BERG), (44, INSEL)]
    ergebnis = analysiere(deck)
    rot = next(f for f in ergebnis["farben"] if f["farbe"] == "R")

    assert rot["laender"] == 12
    assert rot["haertester_bedarf"] == 3
    assert rot["reicht"] is False
    assert rot["fehlende_laender"] > 0
    assert rot["haerteste_karte"] == "Goblin Chainwhirler"


def test_ausreichende_manabasis_wird_nicht_beanstandet():
    deck = [(4, karte("Lightning Bolt", "{R}", cmc=1)), (24, BERG), (32, karte("Ornithopter", "{0}", cmc=0))]
    ergebnis = analysiere(deck)
    rot = next(f for f in ergebnis["farben"] if f["farbe"] == "R")

    assert rot["reicht"] is True
    assert rot["fehlende_laender"] == 0


def test_laender_und_weitere_quellen_werden_getrennt_gezaehlt():
    """Ein Manastein liegt nicht von Anfang an im Spiel -- er wird gezählt,
    aber nicht in die Wahrscheinlichkeit eingerechnet."""
    signet = karte("Boros Signet", "{2}", typ="Artifact", cmc=2, produced=["R", "W"])
    deck = [(4, karte("Lightning Bolt", "{R}", cmc=1)), (4, signet), (20, BERG), (32, INSEL)]
    ergebnis = analysiere(deck)
    rot = next(f for f in ergebnis["farben"] if f["farbe"] == "R")

    assert rot["laender"] == 20
    assert rot["weitere_quellen"] == 4


def test_farbe_ohne_bedarf_und_ohne_quelle_taucht_nicht_auf():
    deck = [(4, karte("Lightning Bolt", "{R}", cmc=1)), (56, BERG)]
    ergebnis = analysiere(deck)

    assert [f["farbe"] for f in ergebnis["farben"]] == ["R"]


def test_haertester_bedarf_schlaegt_die_haeufigkeit():
    """Zwanzig Karten mit einfachem {R} und eine mit {R}{R}{R}: gemessen wird
    an der schwersten Anforderung, sonst wiegt man sich in Sicherheit."""
    deck = [
        (20, karte("Shock", "{R}", cmc=1)),
        (1, karte("Goblin Chainwhirler", "{R}{R}{R}", cmc=3)),
        (39, BERG),
    ]
    ergebnis = analysiere(deck)
    rot = next(f for f in ergebnis["farben"] if f["farbe"] == "R")

    assert rot["haertester_bedarf"] == 3
    assert rot["symbole_gesamt"] == 23


def test_commander_deck_rechnet_mit_99_karten():
    """Im 100-Karten-Deck braucht dieselbe Anforderung mehr Quellen als im
    60-Karten-Deck -- die Rechnung muss die Deckgrösse verwenden."""
    klein = analysiere([(4, karte("Lightning Bolt", "{R}", cmc=1)), (56, BERG)])
    gross = analysiere([(1, karte("Lightning Bolt", "{R}", cmc=1)), (99, BERG)])

    assert klein["deckgroesse"] == 60
    assert gross["deckgroesse"] == 100
    r_klein = next(f for f in klein["farben"] if f["farbe"] == "R")
    r_gross = next(f for f in gross["farben"] if f["farbe"] == "R")
    assert r_gross["empfohlene_laender"] > r_klein["empfohlene_laender"]


def test_leeres_deck_stuerzt_nicht_ab():
    ergebnis = analysiere([])
    assert ergebnis["deckgroesse"] == 0
    assert ergebnis["farben"] == []
