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
    assert farbbedarf("{1}{R}{R}") == {("R",): 2}
    assert farbbedarf("{2}{W}{U}") == {("W",): 1, ("U",): 1}


def test_generisches_mana_zaehlt_nicht():
    assert farbbedarf("{5}") == {}
    assert farbbedarf("") == {}


def test_hybrid_ist_eine_anforderung_an_beide_farben_zusammen():
    """Der gemeldete Fehler: {U/R}{U/R} wurde als "2x Blau UND 2x Rot"
    gezählt. Eclipsed Flamekin ({1}{U/R}{U/R}) galt damit in einem blau-roten
    Deck mit 21 Ländern als nicht bezahlbar -- obwohl JEDES dieser Länder eines
    der beiden Symbole bezahlt. Die Karte braucht zwei Mana aus dem
    gemeinsamen Vorrat."""
    assert farbbedarf("{R/G}") == {("R", "G"): 1}
    assert farbbedarf("{1}{U/R}{U/R}") == {("U", "R"): 2}


def test_farben_stehen_in_wubrg_reihenfolge():
    """Magic nennt Farben immer in dieser Reihenfolge; alphabetisch käme
    "Rot/Blau" heraus."""
    assert list(farbbedarf("{U/R}")) == [("U", "R")]
    assert list(farbbedarf("{G/W}")) == [("W", "G")]


def test_generisch_hybrides_symbol_ist_keine_farbanforderung():
    """{2/R} lässt sich mit zwei generischen Mana bezahlen -- die Karte wird
    nur teurer, sie verlangt kein Rot."""
    assert farbbedarf("{2/R}{2/R}") == {}


def test_phyrexianisches_symbol_ist_keine_farbanforderung():
    """{U/P} lässt sich mit zwei Lebenspunkten bezahlen."""
    assert farbbedarf("{U/P}") == {}
    assert farbbedarf("{1}{W/P}{W/P}") == {}


def test_farbloses_und_generisches_mana_bleiben_aussen_vor():
    assert farbbedarf("{X}{C}{S}{7}") == {}


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


# ----------------------------------------------------------------------
# Der gemeldete Fall: blau-rotes Deck mit Hybridkosten
# ----------------------------------------------------------------------
def test_hybridkarte_zieht_aus_beiden_farben_zusammen():
    """Das gemeldete Deck: 10 Gebirge, 9 Inseln, 2 Länder für beide Farben --
    und Eclipsed Flamekin ({1}{U/R}{U/R}).

    Vorher standen dort zwei Warnungen ("11 zu wenig Blau", "10 zu wenig Rot"),
    weil die Anforderung doppelt gezählt wurde. Richtig ist eine einzige
    Anforderung gegen alle 21 Länder.
    """
    dual = karte("Dual", typ="Land", cmc=0, produced=["U", "R"])
    deck = [
        (10, BERG), (9, INSEL), (2, dual),
        (4, karte("Eclipsed Flamekin", "{1}{U/R}{U/R}", cmc=3)),
        (35, karte("Fueller", "{2}", cmc=2)),
    ]
    ergebnis = analysiere(deck)

    assert len(ergebnis["farben"]) == 1, ergebnis["farben"]
    zeile = ergebnis["farben"][0]
    assert zeile["hybrid"] is True
    assert zeile["farbname"] == "Blau/Rot"
    assert zeile["laender"] == 21, "alle 21 Länder bezahlen eines der Symbole"
    assert zeile["haertester_bedarf"] == 2


def test_land_fuer_zwei_farben_zaehlt_in_der_gruppe_nur_einmal():
    """Ein Land, das Blau UND Rot liefert, bezahlt ein {U/R} genau einmal.
    Doppelt zu zählen würde die Manabasis schönrechnen."""
    dual = karte("Dual", typ="Land", cmc=0, produced=["U", "R"])
    deck = [(20, dual), (4, karte("Hybridkarte", "{U/R}", cmc=1)), (36, karte("Fueller", "{2}", cmc=2))]

    zeile = analysiere(deck)["farben"][0]
    assert zeile["laender"] == 20


def test_reine_und_hybride_anforderung_stehen_nebeneinander():
    deck = [
        (4, karte("Counterspell", "{U}{U}", cmc=2)),
        (4, karte("Hybridkarte", "{U/R}{U/R}", cmc=3)),
        (20, INSEL), (12, BERG), (20, karte("Fueller", "{2}", cmc=2)),
    ]
    zeilen = {f["farbname"]: f for f in analysiere(deck)["farben"]}

    assert set(zeilen) == {"Blau", "Blau/Rot"}
    assert zeilen["Blau"]["laender"] == 20
    assert zeilen["Blau/Rot"]["laender"] == 32


def test_zusatzkosten_machen_aus_einer_karte_keine_manaquelle():
    """"additional" enthält "add". Ohne Wortgrenze galt jede Karte mit
    "as an additional cost, pay {1}{R}" als rote Manaquelle -- und tauchte in
    der Analyse als Quelle einer Farbe auf, die sie nie erzeugt."""
    zusatzkosten = {"name": "Ashling's Command", "type": "Instant",
                    "oracle_text": "As an additional cost to cast this spell, pay {1}{R}."}
    kicker = {"name": "Kicker-Karte", "type": "Creature",
              "oracle_text": "Kicker {2}{U} (You may pay an additional {2}{U} as you cast this spell.)"}

    assert erzeugte_farben(zusatzkosten) == set()
    assert erzeugte_farben(kicker) == set()


def test_manaquelle_in_der_dritten_person_wird_erkannt():
    """Regeltexte schreiben auch "adds" -- die Wortgrenze darf das nicht
    ausschliessen."""
    land = {"name": "Testland", "type": "Land", "oracle_text": "This land adds {G} instead."}
    assert erzeugte_farben(land) == {"G"}


# ----------------------------------------------------------------------
# Mulligan
# ----------------------------------------------------------------------
def test_mulligan_bringt_die_zahlen_auf_die_bekannten_werte():
    """Ohne Mulligan rechnet die Prüfung strenger als die Wirklichkeit: sie
    empfahl 16 Quellen für ein einzelnes Symbol auf Zug 1, die verbreiteten
    Manabasis-Tabellen nennen 14.

    Mit der hier angenommenen Regel (Hände mit weniger als 2 oder mehr als 5
    Ländern werden geworfen, höchstens ein Mulligan) kommen genau die
    bekannten Grössenordnungen heraus -- 60 Karten, 24 Länder, Ziel 90 %.
    """
    from services.manabasis import noetige_quellen_mit_mulligan as noetig

    assert noetig(60, 24, 0, 1) == 14   # 1 Symbol auf Zug 1
    assert noetig(60, 24, 1, 1) == 13   # 1 Symbol auf Zug 2
    assert noetig(60, 24, 2, 1) == 12   # 1 Symbol auf Zug 3
    assert noetig(60, 24, 1, 2) == 20   # 2 Symbole auf Zug 2
    assert noetig(60, 24, 2, 2) == 19   # 2 Symbole auf Zug 3


def test_mulligan_hilft_nur_schlechten_haenden():
    """Die Regel darf die Zahl nicht einfach nach oben schieben: mit reichlich
    Quellen ändert der Mulligan wenig, mit wenigen deutlich mehr."""
    from services.manabasis import wahrscheinlichkeit_mit_mulligan as pm

    viel_ohne = wahrscheinlichkeit(60, 24, 7, 1)
    viel_mit = pm(60, 24, 24, 0, 1)
    wenig_ohne = wahrscheinlichkeit(60, 12, 7, 1)
    wenig_mit = pm(60, 12, 24, 0, 1)

    assert viel_mit > viel_ohne
    assert wenig_mit > wenig_ohne
    assert (wenig_mit - wenig_ohne) > (viel_mit - viel_ohne)


def test_unerreichbares_ziel_wird_als_solches_gemeldet():
    """Drei Symbole auf Zug 3 sind mit 24 Ländern auch dann nicht sicher zu
    haben, wenn ALLE davon die Farbe liefern. Dann hilft keine Umverteilung --
    das muss die Antwort sagen statt eine unerfüllbare Zahl zu nennen."""
    from services.manabasis import noetige_quellen_mit_mulligan as noetig

    assert noetig(60, 24, 2, 3) == 0
    assert noetig(60, 30, 2, 3) > 0


def test_der_gemeldete_fall_reicht_jetzt():
    """Das gemeldete Deck: 21 Länder (10 Gebirge, 9 Inseln, 2 für beide Farben)
    und Eclipsed Flamekin ({1}{U/R}{U/R}). Vorher standen dort zwei Warnungen;
    tatsächlich sind es 21 Quellen für zwei Symbole auf Zug 3."""
    dual = karte("Dual", typ="Land", cmc=0, produced=["U", "R"])
    deck = [
        (10, BERG), (9, INSEL), (2, dual),
        (4, karte("Eclipsed Flamekin", "{1}{U/R}{U/R}", cmc=3)),
        (35, karte("Fueller", "{2}", cmc=2)),
    ]
    zeile = analysiere(deck)["farben"][0]

    assert zeile["reicht"] is True
    assert zeile["wahrscheinlichkeit"] > 0.95
    assert zeile["fehlende_laender"] == 0


# ----------------------------------------------------------------------
# Manasteine und Manakreaturen
# ----------------------------------------------------------------------
def test_manastein_zaehlt_erst_ab_dem_zug_nach_seinen_kosten():
    """Ein Stein für drei Mana hilft einer Karte auf Zug 3 nicht -- er wird
    frühestens in diesem Zug selbst gespielt. Ab Zug 4 zählt er mit."""
    stein = karte("Firdoch Core", "{3}", typ="Artifact", cmc=3,
                  produced=["W", "U", "B", "R", "G"])
    frueh = [(8, stein), (12, BERG), (4, karte("Dreidropp", "{2}{R}", cmc=3)), (36, INSEL)]
    spaet = [(8, stein), (12, BERG), (4, karte("Vierdropp", "{3}{R}", cmc=4)), (36, INSEL)]

    z_frueh = next(f for f in analysiere(frueh)["farben"] if f["farbe"] == "R")
    z_spaet = next(f for f in analysiere(spaet)["farben"] if f["farbe"] == "R")

    assert z_frueh["weitere_quellen"] == 8
    assert z_frueh["weitere_quellen_rechtzeitig"] == 0
    assert z_spaet["weitere_quellen_rechtzeitig"] == 8
    assert z_spaet["quellen"] == 20
    assert z_spaet["wahrscheinlichkeit"] > z_frueh["wahrscheinlichkeit"]


def test_manakreatur_fuer_ein_mana_hilft_ab_zug_zwei():
    vogel = karte("Birds of Paradise", "{G}", typ="Creature — Bird", cmc=1,
                  produced=["W", "U", "B", "R", "G"])
    deck = [(4, vogel), (10, BERG), (4, karte("Zweidropp", "{1}{R}", cmc=2)), (42, INSEL)]

    zeile = next(f for f in analysiere(deck)["farben"] if f["farbe"] == "R")
    assert zeile["weitere_quellen_rechtzeitig"] == 4
    assert zeile["quellen"] == 14
