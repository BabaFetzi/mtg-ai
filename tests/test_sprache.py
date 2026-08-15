"""tests/test_sprache.py -- Sprache der physischen Karte in der Sammlung.

Magic-Karten werden in elf Sprachen gedruckt. Wer eine deutsche Sammlung führt,
muss sie von einer englischen unterscheiden können: beim Tauschen, beim
Verkaufen und beim Zusammenstellen eines Decks. Bisher ging die Angabe beim
Speichern verloren.

Wichtig dabei: eine fehlende Angabe bleibt fehlend. Alte Einträge einfach als
Englisch auszugeben, wäre eine erfundene Angabe.
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
from routers.collection import parse_import_csv, sprache_von

client = TestClient(app)

BOLT = {
    "name": "Lightning Bolt", "type": "Instant", "cmc": 1.0, "colors": ["R"],
    "rarity": "common", "set": "2x2", "price": "2.00", "image": "http://x/b.jpg",
    "prices": {"eur": "2.00", "eur_foil": "8.00"},
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


async def fake_fetch(namen):
    return {"lightning bolt": BOLT}


def _hinzufuegen(maker, nutzlast):
    with patch("routers.collection.get_db_session", _session_patch(maker)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        return client.post("/api/sammlung/hinzufuegen", json=nutzlast, headers=_auth("u"))


# ----------------------------------------------------------------------
# Lesen einer Zeile
# ----------------------------------------------------------------------
def test_fehlende_angabe_bleibt_leer():
    """Altbestand ohne Spalte: keine Angabe, nicht 'Englisch'."""
    assert sprache_von({"sprache": None}) is None
    assert sprache_von({"sprache": ""}) is None
    assert sprache_von({}) is None


def test_sprache_wird_normalisiert():
    assert sprache_von({"sprache": " DE "}) == "de"


# ----------------------------------------------------------------------
# Speichern
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sprache_wird_gespeichert(db):
    antwort = _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                                "album_name": "Test", "bild_url": "", "preis": "2.00",
                                "sprache": "de"})
    assert antwort.status_code == 200

    async with db() as s:
        row = (await s.execute(text("SELECT sprache FROM sammlung_alben"))).mappings().first()
    assert row["sprache"] == "de"


@pytest.mark.asyncio
async def test_ohne_angabe_wird_nichts_erfunden(db):
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00"})

    async with db() as s:
        row = (await s.execute(text("SELECT sprache FROM sammlung_alben"))).mappings().first()
    assert row["sprache"] is None


@pytest.mark.asyncio
async def test_sprache_steht_in_der_sammlungsansicht(db):
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00",
                      "sprache": "ja"})

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.get("/api/sammlung/u", headers=_auth("u"))

    karte = antwort.json()["alben"]["Test"][0]
    assert karte["sprache"] == "ja"


# ----------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------
def test_csv_liest_sprach_und_foilspalte():
    txt = ("Kartenname,Anzahl,Edition,Album,Foil,Sprache\n"
           "Lightning Bolt,2,2x2,Ordner A,ja,de\n")
    out = parse_import_csv(txt, "Default")

    assert out[0]["sprache"] == "de"
    assert out[0]["foil"] is True


def test_csv_ohne_diese_spalten_bleibt_unveraendert():
    """Fremde Exporte kennen die Spalten nicht -- dann bleibt die Angabe leer
    statt geraten."""
    txt = "Kartenname,Anzahl\nLightning Bolt,2\n"
    out = parse_import_csv(txt, "Default")

    assert out[0]["sprache"] == ""
    assert out[0]["foil"] is False


@pytest.mark.asyncio
async def test_export_enthaelt_die_sprachspalte(db):
    _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                      "album_name": "Test", "bild_url": "", "preis": "2.00",
                      "sprache": "de"})

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.get("/api/sammlung/u/export-csv", headers=_auth("u"))

    text_csv = antwort.content.decode("utf-8-sig")
    assert "Sprache" in text_csv.splitlines()[0]
    assert ",de," in text_csv.splitlines()[1]


@pytest.mark.asyncio
async def test_gleiche_karte_in_zwei_sprachen_sind_zwei_zeilen(db):
    """Eine deutsche und eine englische Ausgabe derselben Karte sind für den
    Besitzer nicht dasselbe -- sie dürfen im Export nicht zusammenfallen."""
    for sprache in ("de", "en"):
        _hinzufuegen(db, {"benutzername": "u", "karten_name": "Lightning Bolt",
                          "album_name": "Test", "bild_url": "", "preis": "2.00",
                          "sprache": sprache})

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        antwort = client.get("/api/sammlung/u/export-csv", headers=_auth("u"))

    zeilen = [z for z in antwort.content.decode("utf-8-sig").splitlines() if "Lightning Bolt" in z]
    assert len(zeilen) == 2
