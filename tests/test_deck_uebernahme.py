"""tests/test_deck_uebernahme.py -- fehlende Deckkarten in die Sammlung übernehmen.

Gewünscht: "Wenn man ein Deck gebaut hat, möchte ich die Karten nachträglich in
die Sammlung übernehmen können."

Der heikle Teil ist die Wiederholung: der Knopf darf beim zweiten Druck nicht
alles noch einmal anlegen. Deshalb werden ausschliesslich die FEHLENDEN
Exemplare ergänzt.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from auth import create_access_token
from database import Base
from main import app

client = TestClient(app)

KARTEN = {
    "sol ring": {"name": "Sol Ring", "image": "bild-sol", "price": "1.50", "type": "Artifact",
                 "cmc": 1.0, "colors": [], "rarity": "uncommon", "set": "c21",
                 "prices": {"eur": "1.50", "eur_foil": "9.00"}},
    "lightning bolt": {"name": "Lightning Bolt", "image": "bild-bolt", "price": "3.00",
                       "type": "Instant", "cmc": 1.0, "colors": ["R"], "rarity": "common",
                       "set": "2x2", "prices": {"eur": "3.00"}},
    "mountain": {"name": "Mountain", "image": "bild-berg", "price": "0.10",
                 "type": "Basic Land — Mountain", "cmc": 0.0, "colors": [], "rarity": "common",
                 "set": "2x2", "prices": {"eur": "0.10"}},
}


def _auth(benutzer: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': benutzer})}"}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("INSERT INTO decks (id, benutzername, name, liste, format) "
                 "VALUES (1, 'tester', 'Krenko', :liste, 'commander')"),
            {"liste": "1 Sol Ring\n4 Lightning Bolt\n12 Mountain"},
        )
        await s.execute(
            text("INSERT INTO decks (id, benutzername, name, liste, format) "
                 "VALUES (2, 'jemand-anderes', 'Fremd', '1 Sol Ring', 'commander')")
        )
        await s.commit()
    yield maker
    await engine.dispose()


def _session_patch(maker):
    @asynccontextmanager
    async def _get():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get


async def fake_fetch(namen):
    return {n.lower().strip(): KARTEN[n.lower().strip()]
            for n in namen if n.lower().strip() in KARTEN}


def _uebernehmen(maker, **nutzlast):
    with patch("routers.collection.get_db_session", _session_patch(maker)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.post("/api/sammlung/aus-deck",
                              json={"deck_id": 1, **nutzlast}, headers=_auth("tester"))
    return antwort


async def _bestand(maker):
    async with maker() as s:
        rows = (await s.execute(
            text("SELECT karten_name, album_name, COUNT(*) AS anzahl FROM sammlung_alben "
                 "GROUP BY karten_name, album_name")
        )).mappings().all()
    return {(r["karten_name"], r["album_name"]): r["anzahl"] for r in rows}


@pytest.mark.asyncio
async def test_fehlende_karten_werden_angelegt(db):
    antwort = _uebernehmen(db)

    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    # 1 Sol Ring + 4 Bolts; die 12 Berge sind Standardländer und bleiben aussen vor.
    assert daten["hinzugefuegt"] == 5
    assert daten["uebersprungene_standardlaender"] == 12
    assert daten["album"] == "Krenko"

    bestand = await _bestand(db)
    assert bestand[("Sol Ring", "Krenko")] == 1
    assert bestand[("Lightning Bolt", "Krenko")] == 4


@pytest.mark.asyncio
async def test_zweiter_druck_legt_nichts_doppelt_an(db):
    """Der eigentliche Fallstrick: sonst verdoppelt jeder Druck die Sammlung."""
    _uebernehmen(db)
    zweite = _uebernehmen(db).json()

    assert zweite["hinzugefuegt"] == 0
    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 4


@pytest.mark.asyncio
async def test_vorhandene_exemplare_werden_angerechnet(db):
    async with db() as s:
        for _ in range(3):
            await s.execute(
                text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, "
                     "bild_url, preis) VALUES ('tester', 'Lightning Bolt', 'Alt', '', '0.00')")
            )
        await s.commit()

    daten = _uebernehmen(db).json()

    # 1 Sol Ring + 1 fehlender Bolt.
    assert daten["hinzugefuegt"] == 2
    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 1
    assert bestand[("Lightning Bolt", "Alt")] == 3


@pytest.mark.asyncio
async def test_standardlaender_auf_wunsch_mit(db):
    daten = _uebernehmen(db, mit_standardlaendern=True).json()

    assert daten["hinzugefuegt"] == 17
    assert daten["uebersprungene_standardlaender"] == 0


@pytest.mark.asyncio
async def test_zielordner_frei_waehlbar(db):
    daten = _uebernehmen(db, album_name="Neue Kiste").json()

    assert daten["album"] == "Neue Kiste"
    bestand = await _bestand(db)
    assert ("Sol Ring", "Neue Kiste") in bestand


@pytest.mark.asyncio
async def test_metadaten_und_preis_werden_mitgeschrieben(db):
    """Sonst wäre die Sammlung nach der Übernahme nicht filterbar und der
    Gesamtwert falsch."""
    _uebernehmen(db)

    async with db() as s:
        row = (await s.execute(
            text("SELECT preis, edition, seltenheit, farben, manakosten, kartentyp, foil, sprache "
                 "FROM sammlung_alben WHERE karten_name = 'Lightning Bolt' LIMIT 1")
        )).mappings().first()

    assert row["preis"] == "3.00"
    assert row["edition"] == "2x2"
    assert row["seltenheit"] == "common"
    assert row["farben"] == "R"
    assert row["kartentyp"] == "Instant"
    # Ausführung und Sprache kennt eine Deckliste nicht -- nichts erfinden.
    assert not row["foil"]
    assert row["sprache"] is None


@pytest.mark.asyncio
async def test_fremdes_deck_ist_gesperrt(db):
    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.post("/api/sammlung/aus-deck", json={"deck_id": 2},
                              headers=_auth("tester"))

    assert antwort.status_code == 403
    assert await _bestand(db) == {}


@pytest.mark.asyncio
async def test_unbekanntes_deck_meldet_404(db):
    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.post("/api/sammlung/aus-deck", json={"deck_id": 999},
                              headers=_auth("tester"))

    assert antwort.status_code == 404


def test_ohne_anmeldung_kein_zugriff():
    antwort = client.post("/api/sammlung/aus-deck", json={"deck_id": 1})
    assert antwort.status_code in (401, 403)


# ======================================================================
# Einzelne Karten auswaehlen
# ======================================================================
# Gewuenscht: "dass man die Karten auch einzeln auswaehlen kann, welche man in
# die Sammlung uebernehmen will."
#
# Uebergeben werden NUR NAMEN, keine Stueckzahlen. Wie viele Exemplare fehlen,
# rechnet weiterhin der Server aus Bedarf und Bestand -- eine veraenderte
# Anfrage koennte sonst beliebig viele Karten in die Sammlung schreiben, und
# die Zahl neben dem Namen stimmte nicht mehr mit dem ueberein, was angelegt
# wird.

@pytest.mark.asyncio
async def test_nur_die_ausgewaehlte_karte_wird_uebernommen(db):
    antwort = _uebernehmen(db, nur_karten=["Sol Ring"])

    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["hinzugefuegt"] == 1

    bestand = await _bestand(db)
    assert bestand.get(("Sol Ring", "Krenko")) == 1
    assert ("Lightning Bolt", "Krenko") not in bestand


@pytest.mark.asyncio
async def test_die_anzahl_kommt_vom_server_nicht_aus_der_auswahl(db):
    """Der Name steht in der Auswahl, die MENGE bestimmt der Bedarf.

    Vier Blitzschlaege fehlen -- ein einzelner Name in der Liste legt trotzdem
    alle vier an. Umgekehrt kann niemand ueber die Anfrage mehr anlegen, als
    dem Deck fehlt.
    """
    daten = _uebernehmen(db, nur_karten=["Lightning Bolt"]).json()

    assert daten["hinzugefuegt"] == 4
    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 4


@pytest.mark.asyncio
async def test_keine_auswahl_bedeutet_weiterhin_alles(db):
    """Wer nichts ankreuzt und einfach drueckt, bekommt das bisherige
    Verhalten -- sonst waere die Neuerung eine Verschlechterung."""
    ohne = _uebernehmen(db).json()

    assert ohne["hinzugefuegt"] == 5


@pytest.mark.asyncio
async def test_leere_auswahl_legt_nichts_an(db):
    """Der heikle Unterschied: eine LEERE Liste heisst "nichts angekreuzt",
    nicht "alles". Wuerde man auf Wahrheitswert statt auf None pruefen,
    landete bei null Haekchen die ganze Deckliste in der Sammlung."""
    daten = _uebernehmen(db, nur_karten=[]).json()

    assert daten["hinzugefuegt"] == 0
    assert await _bestand(db) == {}


@pytest.mark.asyncio
async def test_ein_unbekannter_name_in_der_auswahl_schadet_nicht(db):
    """Aus der Oberflaeche kann ein Name kommen, den das Deck gar nicht
    enthaelt. Er wird uebergangen, statt die ganze Uebernahme scheitern zu
    lassen."""
    daten = _uebernehmen(db, nur_karten=["Sol Ring", "Black Lotus"]).json()

    assert daten["hinzugefuegt"] == 1


@pytest.mark.asyncio
async def test_auswahl_greift_auch_bei_doppelseitigen_karten(db):
    """Die Oberflaeche zeigt "Vorderseite // Rueckseite", die Sammlung fuehrt
    oft nur die Vorderseite. Ein Vergleich Zeichen fuer Zeichen wuerde genau
    die Karten uebergehen, die man angekreuzt hat."""
    daten = _uebernehmen(db, nur_karten=["Sol Ring // Irgendwas"]).json()

    assert daten["hinzugefuegt"] == 1


@pytest.mark.asyncio
async def test_standardlaender_lassen_sich_einzeln_auswaehlen(db):
    daten = _uebernehmen(db, nur_karten=["Mountain"], mit_standardlaendern=True).json()

    assert daten["hinzugefuegt"] == 12
    bestand = await _bestand(db)
    assert bestand[("Mountain", "Krenko")] == 12
    assert ("Sol Ring", "Krenko") not in bestand


# ======================================================================
# Stueckzahl anpassen
# ======================================================================
# Gewuenscht: "vielleicht auch die Stueckzahl anpassen."
#
# Die Anzahl ist ein WUNSCH, keine Anweisung. Der Server deckelt sie auf das,
# was wirklich fehlt: weniger nehmen geht, mehr nicht. Ohne diesen Deckel
# koennte eine veraenderte Anfrage die Sammlung aufblaehen, und zweimal
# Druecken wuerde den Bestand verdoppeln.

@pytest.mark.asyncio
async def test_weniger_als_fehlt_laesst_sich_uebernehmen(db):
    """Vier Blitzschlaege fehlen, gekauft hat man erst zwei."""
    daten = _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt", "anzahl": 2}]).json()

    assert daten["hinzugefuegt"] == 2
    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 2


@pytest.mark.asyncio
async def test_der_rest_laesst_sich_spaeter_nachholen(db):
    """Nach einer Teiluebernahme muss der Rest weiterhin als fehlend gelten."""
    _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt", "anzahl": 2}])
    _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt"}])

    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 4


@pytest.mark.asyncio
async def test_mehr_als_fehlt_wird_gedeckelt(db):
    """Die Sicherheitseigenschaft: 999 angefordert, vier fehlen -- vier
    werden angelegt. Sonst koennte eine veraenderte Anfrage die Sammlung
    beliebig aufblaehen."""
    daten = _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt", "anzahl": 999}]).json()

    assert daten["hinzugefuegt"] == 4
    bestand = await _bestand(db)
    assert bestand[("Lightning Bolt", "Krenko")] == 4


@pytest.mark.asyncio
async def test_null_stueck_legt_nichts_an(db):
    daten = _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt", "anzahl": 0},
                                         {"name": "Sol Ring"}]).json()

    assert daten["hinzugefuegt"] == 1
    bestand = await _bestand(db)
    assert ("Lightning Bolt", "Krenko") not in bestand


@pytest.mark.asyncio
async def test_negative_anzahl_zieht_nichts_ab(db):
    """Aus einer veraenderten Anfrage kann eine negative Zahl kommen. Sie darf
    weder als "unendlich" wirken noch Exemplare entfernen."""
    daten = _uebernehmen(db, nur_karten=[{"name": "Lightning Bolt", "anzahl": -5}]).json()

    assert daten["hinzugefuegt"] == 0
    assert await _bestand(db) == {}


@pytest.mark.asyncio
async def test_name_ohne_anzahl_heisst_weiterhin_alles(db):
    """Die alte Schreibweise muss unveraendert gelten -- sonst waere jede
    bestehende Aufrufstelle still kaputt."""
    gemischt = _uebernehmen(db, nur_karten=["Sol Ring",
                                            {"name": "Lightning Bolt", "anzahl": 1}]).json()

    assert gemischt["hinzugefuegt"] == 2
    bestand = await _bestand(db)
    assert bestand[("Sol Ring", "Krenko")] == 1
    assert bestand[("Lightning Bolt", "Krenko")] == 1


# ======================================================================
# Zielordner
# ======================================================================
# Gewuenscht: "dass man bei der Analyse aussuchen kann, in welchen Ordner man
# die Karten aus dem Deck uebernehmen will."

@pytest.mark.asyncio
async def test_karten_landen_im_gewaehlten_ordner(db):
    _uebernehmen(db, album_name="Meine Rares")

    bestand = await _bestand(db)
    assert bestand[("Sol Ring", "Meine Rares")] == 1
    assert ("Sol Ring", "Krenko") not in bestand


@pytest.mark.asyncio
async def test_ohne_ordnerangabe_gilt_der_deckname(db):
    """Das bisherige Verhalten bleibt die Vorbelegung."""
    daten = _uebernehmen(db).json()

    assert daten["album"] == "Krenko"


@pytest.mark.asyncio
async def test_ein_anderer_ordner_zaehlt_trotzdem_als_bestand(db):
    """Der Abgleich schaut auf die ganze Sammlung, nicht auf einen Ordner.
    Wer eine Karte schon in "Handel" liegen hat, soll sie nicht ein zweites
    Mal angelegt bekommen, nur weil ein anderer Ordner gewaehlt ist."""
    _uebernehmen(db, album_name="Handel")
    zweite = _uebernehmen(db, album_name="Krenko").json()

    assert zweite["hinzugefuegt"] == 0
