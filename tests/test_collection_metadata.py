"""
tests/test_collection_metadata.py – Strukturierte Kartenmetadaten (Massnahme 4)

Die Spalten edition/seltenheit/farben/manakosten/kartentyp existierten im
Schema, wurden aber von keinem Insert befüllt -- der Filter musste deshalb alle
Zeilen laden und in Python filtern.

Kritisch bei dieser Umstellung: Alt-Zeilen ohne Metadaten dürfen NICHT aus den
Filterergebnissen verschwinden. Genau das sichern diese Tests ab.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from auth import create_access_token
from database import Base
from routers.collection import karten_metadaten, backfill_kartenmetadaten

client = TestClient(app)


def _auth(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


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


SOL_RING = {
    "name": "Sol Ring", "type": "Artifact", "cmc": 1.0, "colors": [],
    "rarity": "uncommon", "set": "c21", "price": "1.50", "image": "http://x/y.jpg",
}
BOLT = {
    "name": "Lightning Bolt", "type": "Instant", "cmc": 1.0, "colors": ["R"],
    "rarity": "common", "set": "2x2", "price": "2.00", "image": "http://x/b.jpg",
}


# ----------------------------------------------------------------------
# Abbildung Scryfall -> Spalten
# ----------------------------------------------------------------------
def test_metadata_mapping():
    meta = karten_metadaten(BOLT)
    assert meta["edition"] == "2x2"
    assert meta["seltenheit"] == "common"
    assert meta["farben"] == "R"
    assert meta["manakosten"] == 1
    assert meta["kartentyp"] == "Instant"


def test_colorless_card_has_empty_not_null_colors():
    """Wichtig für den Filter: '' bedeutet 'nachweislich farblos',
    NULL bedeutet 'unbekannt'. Beides darf nicht verwechselt werden."""
    assert karten_metadaten(SOL_RING)["farben"] == ""


def test_missing_card_info_yields_nulls():
    meta = karten_metadaten(None)
    assert all(v is None for v in meta.values())


# ----------------------------------------------------------------------
# Speichern
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_added_card_stores_structured_columns(db):
    async def fake_fetch(names):
        return {"lightning bolt": BOLT}

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        resp = client.post(
            "/api/sammlung/hinzufuegen",
            json={"benutzername": "u", "karten_name": "Lightning Bolt",
                  "album_name": "Test", "bild_url": "", "preis": "2.00"},
            headers=_auth("u"),
        )
    assert resp.status_code == 200

    async with db() as s:
        row = (await s.execute(text(
            "SELECT edition, seltenheit, farben, manakosten, kartentyp FROM sammlung_alben"
        ))).mappings().first()

    assert row["edition"] == "2x2"
    assert row["seltenheit"] == "common"
    assert row["farben"] == "R"
    assert row["manakosten"] == 1
    assert row["kartentyp"] == "Instant"


@pytest.mark.asyncio
async def test_placeholder_row_is_not_resolved(db):
    """Der Platzhalter für leere Alben darf keine Scryfall-Abfrage auslösen."""
    aufgerufen = {"ja": False}

    async def fake_fetch(names):
        aufgerufen["ja"] = True
        return {}

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        resp = client.post(
            "/api/sammlung/hinzufuegen",
            json={"benutzername": "u", "karten_name": "__PLACEHOLDER__",
                  "album_name": "Leer", "bild_url": "", "preis": "0.00"},
            headers=_auth("u"),
        )
    assert resp.status_code == 200
    assert aufgerufen["ja"] is False


@pytest.mark.asyncio
async def test_card_is_saved_even_when_scryfall_fails(db):
    """Scryfall-Ausfall darf das Hinzufügen nicht verhindern."""
    async def boom(names):
        raise RuntimeError("Scryfall weg")

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", boom):
        resp = client.post(
            "/api/sammlung/hinzufuegen",
            json={"benutzername": "u", "karten_name": "Sol Ring",
                  "album_name": "Test", "bild_url": "", "preis": "1.50"},
            headers=_auth("u"),
        )
    assert resp.status_code == 200

    async with db() as s:
        row = (await s.execute(text(
            "SELECT karten_name, kartentyp FROM sammlung_alben"
        ))).mappings().first()
    assert row["karten_name"] == "Sol Ring"
    assert row["kartentyp"] is None  # später per Backfill nachfüllbar


# ----------------------------------------------------------------------
# Filter: Alt-Zeilen dürfen nicht verschwinden
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_filter_still_finds_legacy_rows_without_metadata(db):
    """Kernrisiko der Umstellung: eine Zeile OHNE Metadaten (Altbestand) muss
    beim Farbfilter weiterhin gefunden werden."""
    async with db() as s:
        await s.execute(text(
            "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
            "VALUES ('u', 'Lightning Bolt', 'Test', '', '2.00')"
        ))
        await s.commit()

    async def fake_fetch(names):
        return {"lightning bolt": BOLT}

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        resp = client.get("/api/sammlung/u/filter?farbe=R", headers=_auth("u"))

    assert resp.status_code == 200
    karten = resp.json()["karten"]
    assert len(karten) == 1, "Alt-Zeile ohne Metadaten wurde fälschlich herausgefiltert"
    assert karten[0]["name"] == "Lightning Bolt"


@pytest.mark.asyncio
async def test_filter_excludes_non_matching_migrated_rows(db):
    """Zeilen MIT Metadaten werden bereits in SQL korrekt ausgeschlossen."""
    async with db() as s:
        await s.execute(text(
            "INSERT INTO sammlung_alben "
            "(benutzername, karten_name, album_name, bild_url, preis, edition, seltenheit, farben, manakosten, kartentyp) "
            "VALUES ('u', 'Sol Ring', 'Test', '', '1.50', 'c21', 'uncommon', '', 1, 'Artifact')"
        ))
        await s.commit()

    async def fake_fetch(names):
        return {"sol ring": SOL_RING}

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        # Sol Ring ist farblos -> darf beim Rot-Filter nicht erscheinen
        rot = client.get("/api/sammlung/u/filter?farbe=R", headers=_auth("u"))
        # ... aber beim Seltenheitsfilter schon
        selten = client.get("/api/sammlung/u/filter?seltenheit=uncommon", headers=_auth("u"))

    assert rot.json()["karten"] == []
    assert len(selten.json()["karten"]) == 1


# ----------------------------------------------------------------------
# Backfill
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill_fills_legacy_rows(db):
    async with db() as s:
        await s.execute(text(
            "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
            "VALUES ('u', 'Lightning Bolt', 'Test', '', '2.00'), "
            "       ('u', 'Lightning Bolt', 'Test2', '', '2.00')"
        ))
        await s.commit()

    async def fake_fetch(names):
        return {"lightning bolt": BOLT}

    with patch("routers.collection.get_db_session", _session_patch(db)), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        aktualisiert = await backfill_kartenmetadaten()

    assert aktualisiert == 2
    async with db() as s:
        rows = (await s.execute(text("SELECT kartentyp, farben FROM sammlung_alben"))).mappings().all()
    assert all(r["kartentyp"] == "Instant" and r["farben"] == "R" for r in rows)


@pytest.mark.asyncio
async def test_backfill_is_noop_when_nothing_pending(db):
    with patch("routers.collection.get_db_session", _session_patch(db)):
        assert await backfill_kartenmetadaten() == 0
