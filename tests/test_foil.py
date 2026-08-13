"""tests/test_foil.py – Foil-Ausführung und der Sammlungswert

Der Sammlungswert ist das Kernversprechen dieser App -- er muss stimmen.
Zwei Fehler standen dem im Weg:

1. Die Preisauswahl fiel der Reihe nach über eur -> eur_foil -> eur_etched
   durch. Für eine Edition ohne Normalpreis wurde damit der FOIL-Preis für eine
   ganz normale Karte angesetzt. Bei begehrten Karten schnell Faktor fünf.
2. Die Sammlung kannte gar kein Foil-Merkmal. Der Fehler aus Punkt 1 konnte
   deshalb nirgends auffallen -- und eine echte Foil-Karte wurde umgekehrt mit
   dem niedrigeren Normalpreis bewertet.

Bestehende Einträge gelten als NICHT Foil. Das ist die häufigere Ausführung und
die sicherere Annahme: sie bewertet eher zu niedrig als zu hoch.
"""

import sqlite3
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from main import app
from auth import create_access_token
from database import Base
from routers.collection import ist_foil, live_preis_fuer
from services.scryfall import preis_fuer_variante

client = TestClient(app)

PREISE = {"eur": "5.00", "eur_foil": "25.00"}


def _auth(user: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': user})}"}


# ----------------------------------------------------------------------
# Preisauswahl
# ----------------------------------------------------------------------
def test_normale_karte_bekommt_den_normalpreis():
    assert preis_fuer_variante(PREISE, foil=False) == "5.00"


def test_foil_karte_bekommt_den_foilpreis():
    assert preis_fuer_variante(PREISE, foil=True) == "25.00"


def test_ohne_normalpreis_wird_nicht_auf_foil_ausgewichen():
    """Der eigentliche Fehler: 25.00 für eine normale Karte."""
    assert preis_fuer_variante({"eur": None, "eur_foil": "25.00"}, foil=False) is None


def test_ohne_foilpreis_wird_nicht_auf_normal_ausgewichen():
    assert preis_fuer_variante({"eur": "5.00", "eur_foil": None}, foil=True) is None


# ----------------------------------------------------------------------
# Alt-Zeilen ohne Foil-Spalte
# ----------------------------------------------------------------------
def test_fehlende_foil_angabe_gilt_als_nicht_foil():
    assert ist_foil({"foil": None}) is False
    assert ist_foil({}) is False
    assert ist_foil({"foil": 0}) is False
    assert ist_foil({"foil": 1}) is True
    assert ist_foil({"foil": True}) is True


def test_live_preis_faellt_auf_gespeicherten_wert_zurueck():
    """Liegt für die Ausführung kein Preis vor, ist der zuletzt gespeicherte
    Wert die bessere Antwort als der Preis der anderen Ausführung."""
    card_info = {"prices": {"eur": "5.00"}}
    assert live_preis_fuer(card_info, {"foil": True}, "9.99") == "9.99"
    assert live_preis_fuer(card_info, {"foil": False}, "9.99") == "5.00"
    assert live_preis_fuer(None, {"foil": False}, "9.99") == "9.99"


# ----------------------------------------------------------------------
# Migration einer bestehenden Datenbank
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_ergaenzt_die_spalte_und_erhaelt_die_daten():
    """create_all legt nur fehlende TABELLEN an, keine fehlenden Spalten. Ohne
    ausdrücklichen Schritt würde jeder Zugriff auf die neue Spalte bei einer
    bestehenden Installation scheitern."""
    import database

    with tempfile.TemporaryDirectory() as ordner:
        pfad = str(Path(ordner) / "alt.db")
        con = sqlite3.connect(pfad)
        con.execute(
            "CREATE TABLE sammlung_alben ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername VARCHAR(50), "
            "karten_name VARCHAR(255) NOT NULL, album_name VARCHAR(100), bild_url TEXT, "
            "preis VARCHAR(50), scryfall_id VARCHAR(36), edition VARCHAR(20), "
            "seltenheit VARCHAR(20), farben VARCHAR(20), manakosten INTEGER, "
            "kartentyp VARCHAR(100), anzahl INTEGER, zustand VARCHAR(20), "
            "hinzugefuegt_am TIMESTAMP)"
        )
        con.execute("INSERT INTO sammlung_alben (benutzername, karten_name) VALUES ('alt', 'Sol Ring')")
        con.commit()

        engine = create_async_engine(f"sqlite+aiosqlite:///{pfad}")
        try:
            async with engine.begin() as conn:
                await database._spalte_ergaenzen(conn, "sammlung_alben", "foil", "BOOLEAN DEFAULT 0")
                # Zweiter Aufruf muss folgenlos bleiben.
                await database._spalte_ergaenzen(conn, "sammlung_alben", "foil", "BOOLEAN DEFAULT 0")
        finally:
            await engine.dispose()

        spalten = [r[1] for r in con.execute("PRAGMA table_info(sammlung_alben)")]
        assert "foil" in spalten
        # Bestandsdaten unberührt, und als "nicht Foil" geführt.
        assert con.execute("SELECT karten_name, foil FROM sammlung_alben").fetchall() == [("Sol Ring", 0)]
        con.close()


# ----------------------------------------------------------------------
# Durchgängig: hinzufügen und wieder auslesen
# ----------------------------------------------------------------------
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


def _fabrik(macher):
    @asynccontextmanager
    async def _get_db_session():
        async with macher() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get_db_session


async def _karten_daten(namen):
    return {"sol ring": {
        "name": "Sol Ring", "image": "", "type": "Artifact", "colors": [],
        "cmc": 1, "rarity": "uncommon", "set": "c21",
        "price": "5.00", "prices": PREISE,
    }}


@pytest.mark.asyncio
async def test_foil_karte_wird_mit_foilpreis_gespeichert_und_angezeigt(db):
    with patch("routers.collection.get_db_session", _fabrik(db)), \
         patch("routers.collection.fetch_card_details_cached", _karten_daten):

        for foil in (False, True):
            antwort = client.post(
                "/api/sammlung/hinzufuegen",
                json={"benutzername": "sammler", "karten_name": "Sol Ring",
                      "album_name": "Standard", "preis": "0.00", "foil": foil},
                headers=_auth("sammler"),
            )
            assert antwort.status_code == 200, antwort.text

        alben = client.get("/api/sammlung/sammler", headers=_auth("sammler")).json()["alben"]
        karten = alben["Standard"]

    assert len(karten) == 2
    normal = next(k for k in karten if not k["foil"])
    glanz = next(k for k in karten if k["foil"])

    assert normal["livePreis"] == "5.00"
    assert glanz["livePreis"] == "25.00", "Die Foil-Karte muss mit dem Foil-Preis bewertet werden"


@pytest.mark.asyncio
async def test_ohne_angabe_gilt_eine_karte_als_nicht_foil(db):
    """Der Standard muss die sichere Annahme sein -- eine fälschlich als Foil
    geführte Karte würde den Sammlungswert nach oben verfälschen."""
    with patch("routers.collection.get_db_session", _fabrik(db)), \
         patch("routers.collection.fetch_card_details_cached", _karten_daten):

        client.post(
            "/api/sammlung/hinzufuegen",
            json={"benutzername": "sammler", "karten_name": "Sol Ring", "album_name": "Standard"},
            headers=_auth("sammler"),
        )
        karten = client.get("/api/sammlung/sammler", headers=_auth("sammler")).json()["alben"]["Standard"]

    assert karten[0]["foil"] is False
    assert karten[0]["livePreis"] == "5.00"
