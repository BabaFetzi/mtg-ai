"""Die Sammlung ohne die 4,5 MB.

Die Ordneruebersicht, die Top-Liste und die Ordnerauswahl haben bisher jeweils
die VOLLSTAENDIGE Sammlung geladen, um daraus Summen, zehn Karten oder eine
Namensliste zu gewinnen. Bei 15000 Karten sind das 4,5 MB pro Ansicht.

Der Gewinn ist nur echt, wenn dabei dasselbe herauskommt. Diese Tests pruefen
darum vor allem: Zeigt der Server denselben Wert an, den der Browser vorher
gerechnet hat?
"""

import json

import pytest

from routers.collection import (MAX_PRO_SEITE, SORTIERUNGEN, STANDARD_PRO_SEITE,
                                _filter_antwort, _top_antwort, _uebersicht_bauen,
                                karten_preis, preis_zahl, sortiere_karten)


def zeile(id, name, album, preis, foil=0, bild="http://x/y.jpg"):
    return {"id": id, "karten_name": name, "album_name": album, "preis": preis,
            "bild_url": bild, "foil": foil}


# ----------------------------------------------------------------------
# preis_zahl -- muss parseFloat nachbilden, sonst aendern sich die Summen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("eingabe,erwartet", [
    ("1.50", 1.50),
    ("1,50", 1.50),          # deutsches Komma
    ("1.50 €", 1.50),        # parseFloat liest bis zum ersten Unsinn
    ("", 0.0),               # parseFloat -> NaN, "|| 0" -> 0
    ("abc", 0.0),
    (None, 0.0),
    (0, 0.0),
    (12.34, 12.34),
    ("0.00", 0.0),
    (".5", 0.5),
    ("-3.20", -3.20),
    # String.replace(",", ".") ersetzt nur das ERSTE Komma -- parseFloat liest
    # danach 1.234. Absichtlich nachgebaut statt "repariert": eine Korrektur
    # wuerde andere Summen ergeben als die bisher angezeigten.
    ("1,234,56", 1.234),
])
def test_preis_zahl_liest_wie_der_browser(eingabe, erwartet):
    assert preis_zahl(eingabe) == pytest.approx(erwartet)


def test_wahrheitswerte_zaehlen_nicht_als_preis():
    # bool ist in Python ein int -- ohne Sonderfall waere True ein Euro.
    assert preis_zahl(True) == 0.0
    assert preis_zahl(False) == 0.0


def test_karten_preis_faellt_auf_den_gespeicherten_preis_zurueck():
    assert karten_preis({"livePreis": "2.00", "preis": "9.99"}) == pytest.approx(2.0)
    assert karten_preis({"livePreis": "", "preis": "9.99"}) == pytest.approx(9.99)
    assert karten_preis({"livePreis": None, "preis": None}) == 0.0


# ----------------------------------------------------------------------
# Uebersicht
# ----------------------------------------------------------------------
def test_uebersicht_summiert_wie_die_alte_ansicht():
    rows = [
        zeile(1, "Sol Ring", "Ordner A", "1.50"),
        zeile(2, "Black Lotus", "Ordner A", "100.00"),
        zeile(3, "Forest", "Ordner B", "0.10"),
    ]

    daten = _uebersicht_bauen(rows, {})
    nach_name = {a["name"]: a for a in daten["alben"]}

    assert nach_name["Ordner A"]["anzahl"] == 2
    assert nach_name["Ordner A"]["wert"] == pytest.approx(101.50)
    assert nach_name["Ordner B"]["wert"] == pytest.approx(0.10)
    assert daten["gesamtwert"] == pytest.approx(101.60)


def test_wunschliste_zaehlt_nicht_zum_sammlungswert():
    """Die Wunschliste ist kein Besitz -- das Frontend hat sie
    herausgerechnet, der Server muss das genauso tun."""
    rows = [
        zeile(1, "Sol Ring", "Ordner A", "1.50"),
        zeile(2, "Black Lotus", "Wunschliste", "10000.00"),
    ]

    daten = _uebersicht_bauen(rows, {})

    assert [a["name"] for a in daten["alben"]] == ["Ordner A"]
    assert daten["gesamtwert"] == pytest.approx(1.50)
    assert daten["wunschliste"] == {"anzahl": 1, "wert": 10000.00}


def test_leerer_ordner_bleibt_sichtbar_und_zaehlt_keine_karte():
    """Ein leerer Ordner wird durch eine Platzhalterzeile am Leben gehalten.
    Zaehlte sie mit, stuende bei jedem neuen Ordner "1 Karte"."""
    rows = [zeile(1, "__PLACEHOLDER__", "Leerer Ordner", "0.00")]

    daten = _uebersicht_bauen(rows, {})

    assert len(daten["alben"]) == 1
    assert daten["alben"][0]["name"] == "Leerer Ordner"
    assert daten["alben"][0]["anzahl"] == 0
    assert daten["alben"][0]["vorschau"] == []
    assert daten["gesamtwert"] == 0.0


def test_vorschau_zeigt_die_wertvollsten_karten():
    rows = [zeile(i, f"Karte {i}", "Ordner A", f"{i}.00") for i in range(1, 9)]

    alben = _uebersicht_bauen(rows, {})["alben"]

    vorschau = [k["name"] for k in alben[0]["vorschau"]]
    assert vorschau == ["Karte 8", "Karte 7", "Karte 6", "Karte 5"]


def test_uebersicht_nutzt_den_livepreis_nicht_den_gespeicherten():
    """Der gespeicherte Preis kann Monate alt sein. Die Uebersicht zeigt den
    aktuellen -- genau wie die alte Ansicht, die livePreis bevorzugt hat."""
    rows = [zeile(1, "Sol Ring", "Ordner A", "1.00")]
    daten_je_zeile = {1: {"name": "Sol Ring", "prices": {"eur": "7.50"}}}

    daten = _uebersicht_bauen(rows, daten_je_zeile)

    assert daten["gesamtwert"] == pytest.approx(7.50)


def test_foilpreis_zaehlt_fuer_foilkarten():
    """Eine Foil-Karte ist ein Vielfaches wert. Nimmt die Summe den
    Normalpreis, ist der Sammlungswert systematisch zu niedrig."""
    rows = [zeile(1, "Sol Ring", "Ordner A", "1.00", foil=1)]
    daten_je_zeile = {1: {"name": "Sol Ring",
                          "prices": {"eur": "7.50", "eur_foil": "42.00"}}}

    assert _uebersicht_bauen(rows, daten_je_zeile)["gesamtwert"] == pytest.approx(42.00)


# ----------------------------------------------------------------------
# Top-Liste
# ----------------------------------------------------------------------
def test_top_liefert_die_teuersten_mit_ordnernamen():
    rows = [zeile(i, f"Karte {i}", f"Ordner {i % 2}", f"{i}.00") for i in range(1, 21)]

    daten = json.loads(_top_antwort(rows, {}, 3).body)

    assert [k["name"] for k in daten["karten"]] == ["Karte 20", "Karte 19", "Karte 18"]
    # Ohne den Ordnernamen kann die Liste nicht zeigen, wo die Karte liegt.
    assert daten["karten"][0]["albumName"] == "Ordner 0"


def test_top_bleibt_unter_dem_limit_auch_bei_wenigen_karten():
    rows = [zeile(1, "Sol Ring", "Ordner A", "1.50")]

    daten = json.loads(_top_antwort(rows, {}, 10).body)

    assert len(daten["karten"]) == 1


# ----------------------------------------------------------------------
# Blaettern
# ----------------------------------------------------------------------
def _seite(rows, seite, pro_seite, sortierung="name"):
    return json.loads(_filter_antwort(
        rows, {r["id"]: {"name": r["karten_name"]} for r in rows},
        None, None, None, None, None, None, None, seite, pro_seite, sortierung).body)


def test_blaettern_schneidet_die_richtige_seite():
    rows = [zeile(i, f"Karte {i:03}", "Ordner A", "1.00") for i in range(1, 251)]

    erste = _seite(rows, 1, 100)
    zweite = _seite(rows, 2, 100)
    dritte = _seite(rows, 3, 100)

    assert len(erste["karten"]) == 100
    assert len(zweite["karten"]) == 100
    assert len(dritte["karten"]) == 50
    assert erste["karten"][0]["name"] == "Karte 001"
    assert zweite["karten"][0]["name"] == "Karte 101"
    # Ohne die Gesamtzahl kann die Ansicht weder "100 von 250" anzeigen noch
    # wissen, wann sie aufhoeren muss nachzuladen.
    assert erste["gesamt"] == 250


def test_seiten_ueberschneiden_sich_nicht_und_lassen_nichts_aus():
    rows = [zeile(i, f"Karte {i:03}", "Ordner A", "1.00") for i in range(1, 251)]

    gesehen = []
    for s in (1, 2, 3):
        gesehen += [k["name"] for k in _seite(rows, s, 100)["karten"]]

    assert len(gesehen) == len(set(gesehen)) == 250


def test_seite_hinter_dem_ende_ist_leer_statt_ein_fehler():
    """Beim schnellen Klicken auf "Mehr laden" kann eine Seite angefragt
    werden, die es nicht mehr gibt. Das darf keinen Fehler geben."""
    rows = [zeile(1, "Sol Ring", "Ordner A", "1.50")]

    daten = _seite(rows, 99, 100)

    assert daten["karten"] == []
    assert daten["gesamt"] == 1


# ----------------------------------------------------------------------
# Sortierung -- muss auf dem Server passieren, sonst luegt sie beim Blaettern
# ----------------------------------------------------------------------
def _sortiert(karten, sortierung):
    return [k["name"] for k in sortiere_karten(karten, sortierung)]


def test_nach_namen_wie_localecompare():
    karten = [{"name": n} for n in ["Zur", "ätherling", "Birds", "Ætherling", "abc"]]

    # Akzente und Ligaturen gehoeren zum Grundbuchstaben. Ohne das landet
    # "ätherling" hinter "Zur", weil Pythons Standardvergleich nach
    # Zeichencode sortiert.
    assert _sortiert(karten, "name") == ["abc", "Ætherling", "ätherling", "Birds", "Zur"]


def test_gross_und_kleinschreibung_egal():
    karten = [{"name": n} for n in ["banana", "Apple", "apple", "Banana"]]

    namen = _sortiert(karten, "name")

    assert namen[:2] == ["Apple", "apple"] or namen[:2] == ["apple", "Apple"]
    assert namen[2:] == ["Banana", "banana"] or namen[2:] == ["banana", "Banana"]


def test_preissortierung_wirkt_ueberhaupt():
    """Frueher hiess der Preis im Filter "price", ueberall sonst "livePreis".
    Der Browser las "livePreis", bekam es hier nicht und rechnete mit 0 --
    "nach Preis sortieren" hat in der Ordneransicht nie etwas getan."""
    karten = [
        {"name": "Billig", "livePreis": "1.00", "preis": "1.00"},
        {"name": "Teuer", "livePreis": "480.00", "preis": "12.00"},
        {"name": "Mittel", "livePreis": "20.00", "preis": "20.00"},
    ]

    assert _sortiert(karten, "priceDesc") == ["Teuer", "Mittel", "Billig"]
    assert _sortiert(karten, "priceAsc") == ["Billig", "Mittel", "Teuer"]


def test_filter_liefert_dieselben_feldnamen_wie_die_uebersicht():
    """Eine Kartenform fuer alle Ansichten. Zwei Formen fuer dieselbe Sache
    waren die Ursache dafuer, dass die Preissortierung ins Leere lief."""
    rows = [zeile(1, "Sol Ring", "Ordner A", "1.50")]
    daten = {1: {"name": "Sol Ring", "prices": {"eur": "7.50"}, "set": "c21",
                 "image": "http://x/y.jpg", "type": "Artifact", "rarity": "uncommon"}}

    aus_filter = json.loads(_filter_antwort(
        rows, daten, None, None, None, None, None, None, None,
        1, 100, "name").body)["karten"][0]
    aus_uebersicht = _uebersicht_bauen(rows, daten)["alben"][0]["vorschau"][0]

    for feld in ("id", "name", "bild_url", "preis", "livePreis", "foil",
                 "sprache", "zustand", "edition", "sammlernummer"):
        assert feld in aus_filter, f"{feld} fehlt in der Filterantwort"
        assert feld in aus_uebersicht, f"{feld} fehlt in der Uebersicht"
    assert aus_filter["livePreis"] == aus_uebersicht["livePreis"]
    # Die alten Sondernamen dieser einen Ansicht darf es nicht mehr geben.
    for alt in ("image_url", "price", "originalPrice"):
        assert alt not in aus_filter, f"{alt} ist wieder da"


def test_sortierung_nach_manakosten_und_seltenheit():
    nach_cmc = [{"name": "A", "cmc": 5}, {"name": "B", "cmc": 0}, {"name": "C", "cmc": 2}]
    assert _sortiert(nach_cmc, "cmc") == ["B", "C", "A"]

    nach_seltenheit = [{"name": "A", "rarity": "common"}, {"name": "B", "rarity": "mythic"},
                       {"name": "C", "rarity": "rare"}]
    assert _sortiert(nach_seltenheit, "rarity") == ["B", "C", "A"]


def test_gleichstand_wird_eindeutig_aufgeloest():
    """Bei gleichem Preis muss die Reihenfolge feststehen. Sonst kann
    dieselbe Karte beim Blaettern auf zwei Seiten auftauchen -- oder auf
    keiner."""
    karten = [{"name": n, "price": "1.00"} for n in ["Charlie", "Alpha", "Bravo"]]

    assert _sortiert(karten, "priceDesc") == ["Alpha", "Bravo", "Charlie"]
    assert _sortiert(karten, "priceAsc") == ["Alpha", "Bravo", "Charlie"]


def test_sortierung_wirkt_ueber_die_seitengrenze_hinweg():
    """Der Kern der Sache: die teuerste Karte liegt hinten in der Zeilenfolge.
    Sortierte erst der Browser die geladene Seite, waere sie unsichtbar."""
    rows = [zeile(i, f"Karte {i:03}", "Ordner A", "1.00") for i in range(1, 201)]
    rows.append(zeile(999, "Black Lotus", "Ordner A", "9999.00"))
    daten = {r["id"]: {"name": r["karten_name"], "prices": {"eur": r["preis"]}}
             for r in rows}

    erste_seite = json.loads(_filter_antwort(
        rows, daten, None, None, None, None, None, None, None,
        1, 100, "priceDesc").body)

    assert erste_seite["karten"][0]["name"] == "Black Lotus"
    assert erste_seite["gesamt"] == 201


def test_unbekannte_sortierung_faellt_auf_den_namen_zurueck():
    karten = [{"name": "B"}, {"name": "A"}]

    assert _sortiert(karten, "voelliger-unsinn") == ["A", "B"]


def test_grenzen_sind_gesetzt():
    # Ohne Obergrenze koennte ?pro_seite=999999 die ganze Sammlung
    # in einem Stueck anfordern -- genau das, was behoben werden sollte.
    assert STANDARD_PRO_SEITE == 100
    assert MAX_PRO_SEITE >= STANDARD_PRO_SEITE
