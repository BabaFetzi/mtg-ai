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
