"""tests/test_druck_und_zustand.py -- welche Auflage liegt im Ordner?

Die Sammlung hielt bisher nur den Kartennamen fest. Preis, Edition und
Seltenheit kamen deshalb immer vom Standarddruck -- also vom neuesten
Nachdruck. Wer einen alten Druck besitzt, sah dessen Wert nie: bei alten Karten
liegt zwischen Erstausgabe und Nachdruck schnell das Zehnfache.

Ebenso fehlte der Zustand. Die Spalte gab es im Schema, gefüllt wurde sie nie.
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
from routers.collection import ZUSTAENDE, druck_von, zustand_von

client = TestClient(app)

# Derselbe Bolt in zwei Auflagen: alt und teuer, neu und billig.
ALTER_DRUCK = {
    "name": "Lightning Bolt", "type": "Instant", "cmc": 1.0, "colors": ["R"],
    "rarity": "common", "set": "lea", "set_name": "Limited Edition Alpha",
    "image": "http://x/alpha.jpg", "price": "480.00",
    "prices": {"eur": "480.00", "eur_foil": None},
    "scryfall_id": "alpha-id", "sammlernummer": "161",
}
NEUER_DRUCK = {
    "name": "Lightning Bolt", "type": "Instant", "cmc": 1.0, "colors": ["R"],
    "rarity": "common", "set": "2x2", "set_name": "Double Masters 2022",
    "image": "http://x/2x2.jpg", "price": "2.00",
    "prices": {"eur": "2.00", "eur_foil": "9.00"},
    "scryfall_id": "2x2-id", "sammlernummer": "117",
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
    yield async_sessionmaker(engine, expire_on_commit=False)
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


async def falscher_druck(kennung):
    return {"alpha-id": ALTER_DRUCK, "2x2-id": NEUER_DRUCK}.get(kennung)


async def falsche_druecke(kennungen):
    alle = {"alpha-id": ALTER_DRUCK, "2x2-id": NEUER_DRUCK}
    return {k: alle[k] for k in kennungen if k in alle}


async def falsche_namen(namen):
    # Über den Namen kommt immer der Standarddruck -- genau das war der Fehler.
    return {"lightning bolt": NEUER_DRUCK}


def _hinzufuegen(maker, nutzlast):
    with patch("routers.collection.get_db_session", _session_patch(maker)), \
         patch("routers.collection.druck_nach_id", falscher_druck), \
         patch("routers.collection.fetch_card_details_cached", falsche_namen):
        return client.post("/api/sammlung/hinzufuegen", json=nutzlast, headers=_auth("u"))


def _sammlung(maker):
    with patch("routers.collection.get_db_session", _session_patch(maker)), \
         patch("routers.collection.druecke_nach_ids", falsche_druecke), \
         patch("routers.collection.fetch_card_details_cached", falsche_namen):
        return client.get("/api/sammlung/u", headers=_auth("u")).json()


# ----------------------------------------------------------------------
# Lesen einer Zeile
# ----------------------------------------------------------------------
def test_fehlende_angaben_bleiben_leer():
    """Altbestand: keine Auflage, kein Zustand -- und nichts wird erfunden."""
    assert druck_von({"edition": None, "sammlernummer": None, "scryfall_id": None}) == {
        "edition": None, "sammlernummer": None, "scryfall_id": None}
    assert zustand_von({"zustand": None}) is None
    assert zustand_von({}) is None


def test_unbekannter_zustand_wird_nicht_ausgegeben():
    assert zustand_von({"zustand": "XYZ"}) is None
    assert zustand_von({"zustand": " nm "}) == "NM"


# ----------------------------------------------------------------------
# Speichern
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gewaehlter_druck_bestimmt_den_preis(db):
    """Der Kern: wer die Alpha-Ausgabe auswählt, bekommt deren Preis -- nicht
    die 2 Euro des Nachdrucks."""
    antwort = _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                                "album_name": "Test", "bild_url": "", "preis": "2.00",
                                "scryfall_id": "alpha-id", "edition": "lea",
                                "sammlernummer": "161"})
    assert antwort.status_code == 200

    async with db() as s:
        row = (await s.execute(text(
            "SELECT preis, edition, sammlernummer, scryfall_id, seltenheit FROM sammlung_alben"
        ))).mappings().first()

    assert row["preis"] == "480.00"
    assert row["edition"] == "lea"
    assert row["sammlernummer"] == "161"
    assert row["scryfall_id"] == "alpha-id"


@pytest.mark.asyncio
async def test_ohne_druckangabe_bleibt_es_beim_standarddruck(db):
    """Altverhalten für Wege, die keinen Druck kennen (CSV, Schnellhinzufügen)
    -- eine Zeile ohne Preis wäre schlechter als eine mit ungefährem."""
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00"})

    async with db() as s:
        row = (await s.execute(text(
            "SELECT preis, edition, scryfall_id FROM sammlung_alben"))).mappings().first()

    assert row["preis"] == "2.00"
    assert row["scryfall_id"] is None


@pytest.mark.asyncio
async def test_zustand_wird_gespeichert(db):
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00",
                      "zustand": "lp"})

    async with db() as s:
        row = (await s.execute(text("SELECT zustand FROM sammlung_alben"))).mappings().first()
    assert row["zustand"] == "LP"


@pytest.mark.asyncio
async def test_unbekannter_zustand_wird_abgelehnt(db):
    """Lieber ein klarer Fehler als eine stillschweigend falsche Angabe über
    fremdes Eigentum."""
    antwort = _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                                "album_name": "Test", "bild_url": "", "preis": "2.00",
                                "zustand": "super"})
    assert antwort.status_code == 400

    async with db() as s:
        anzahl = (await s.execute(text("SELECT COUNT(*) FROM sammlung_alben"))).scalar()
    assert anzahl == 0


def test_zustandsskala_ist_die_uebliche():
    assert set(ZUSTAENDE) == {"M", "NM", "EX", "GD", "LP", "PL", "PO"}


# ----------------------------------------------------------------------
# Anzeige
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sammlung_zeigt_auflage_zustand_und_richtigen_preis(db):
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00",
                      "scryfall_id": "alpha-id", "edition": "lea",
                      "sammlernummer": "161", "zustand": "EX"})

    karte = _sammlung(db)["alben"]["Test"][0]

    assert karte["edition"] == "lea"
    assert karte["edition_name"] == "Limited Edition Alpha"
    assert karte["sammlernummer"] == "161"
    assert karte["zustand"] == "EX"
    # Der Live-Preis kommt aus dem gespeicherten Druck, nicht vom Nachdruck.
    assert karte["livePreis"] == "480.00"


@pytest.mark.asyncio
async def test_altbestand_ohne_druck_verschwindet_nicht(db):
    """Kernrisiko der Umstellung: Zeilen ohne Druckangabe müssen weiter
    angezeigt und bewertet werden."""
    async with db() as s:
        await s.execute(text(
            "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
            "VALUES ('u', 'Lightning Bolt', 'Alt', '', '1.00')"))
        await s.commit()

    karten = _sammlung(db)["alben"]["Alt"]
    assert len(karten) == 1
    assert karten[0]["livePreis"] == "2.00", "fällt auf den Standarddruck zurück"
    assert karten[0]["edition"] is None


# ----------------------------------------------------------------------
# Das Antwortschema
# ----------------------------------------------------------------------
def test_antwortschema_liefert_die_druckangaben_aus():
    """Beim Bauen zugeschnappt: das Antwortmodell filtert alles heraus, was
    nicht darin steht. Der Endpunkt lieferte Kennung, Set und Sammlernummer --
    beim Client kamen sie nie an, und die Oberfläche hätte stillschweigend
    wieder den Standarddruck gespeichert. Kein Test hätte das gemerkt, weil
    alle direkt gegen die Funktion prüften."""
    from schemas.models import CardPrint

    felder = set(CardPrint.model_fields)
    assert {"id", "set", "sammlernummer"} <= felder, (
        "Ohne diese Felder lässt sich die besessene Auflage nicht übertragen")

    druck = CardPrint(id="abc", set="lea", set_name="Limited Edition Alpha",
                      sammlernummer="161", preis="480.00")
    ausgabe = druck.model_dump()
    assert ausgabe["id"] == "abc"
    assert ausgabe["set"] == "lea"
    assert ausgabe["sammlernummer"] == "161"
