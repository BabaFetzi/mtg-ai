"""
tests/test_csv_import.py

Deckt den CSV-Import-Bug ab: Nach einem Import zeigten Alben falsche/fremde Karten,
weil das Parsing fragil war (nur Komma-Delimiter, feste Spaltenpositionen, keine
Mengen-Bereinigung). Deutsches Excel (Semikolon) schlug komplett fehl; führende
Mengen ('1 Sol Ring') und vertauschte Spalten wurden falsch zugeordnet.

Zwei Ebenen:
1. parse_import_csv(): reine Parser-Unit-Tests (Delimiter, Header-Mapping, Menge).
2. End-to-End gegen eine echte In-Memory-DB: mehrere Karten in mehrere Alben
   importieren und prüfen, dass jedes Album GENAU seine eigenen Karten liefert.
"""

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch

from main import app
from auth import create_access_token
from database import Base
from routers.collection import parse_import_csv, run_csv_import_task

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


# ======================================================================
# 1. Parser-Unit-Tests (kein Netzwerk, keine DB)
# ======================================================================
def test_parse_comma():
    txt = "Kartenname,Anzahl,Edition,Album\nSol Ring,1,C21,Ordner A\nLightning Bolt,2,M10,Ordner B\n"
    out = parse_import_csv(txt, "Default")
    assert out == [
        {"name": "Sol Ring", "anzahl": 1, "edition": "C21", "album": "Ordner A"},
        {"name": "Lightning Bolt", "anzahl": 2, "edition": "M10", "album": "Ordner B"},
    ]


def test_parse_semicolon_german_excel():
    # Deutsches Excel: Semikolon + CRLF -- schlug vorher komplett fehl.
    txt = "Kartenname;Anzahl;Edition;Album\r\nSol Ring;1;C21;Ordner A\r\nLightning Bolt;2;M10;Ordner B\r\n"
    out = parse_import_csv(txt, "Default")
    assert [(e["name"], e["anzahl"], e["album"]) for e in out] == [
        ("Sol Ring", 1, "Ordner A"),
        ("Lightning Bolt", 2, "Ordner B"),
    ]


def test_parse_tab_delimited():
    txt = "Kartenname\tAnzahl\tEdition\tAlbum\nSol Ring\t1\tC21\tOrdner A\n"
    out = parse_import_csv(txt, "Default")
    assert out[0]["name"] == "Sol Ring" and out[0]["album"] == "Ordner A"


def test_parse_leading_quantity_in_name():
    # Moxfield/Archidekt-Stil: Menge steckt im Namen.
    txt = "Kartenname,Album\n1 Sol Ring,Ordner A\n2x Lightning Bolt,Ordner B\n3X Forest,Ordner B\n"
    out = parse_import_csv(txt, "Default")
    assert out == [
        {"name": "Sol Ring", "anzahl": 1, "edition": "", "album": "Ordner A"},
        {"name": "Lightning Bolt", "anzahl": 2, "edition": "", "album": "Ordner B"},
        {"name": "Forest", "anzahl": 3, "edition": "", "album": "Ordner B"},
    ]


def test_parse_reordered_columns_by_header():
    # Spaltenreihenfolge anders -> Header-Mapping muss greifen (nicht Position).
    txt = "Album,Anzahl,Kartenname\nOrdner A,1,Sol Ring\nOrdner B,3,Llanowar Elves\n"
    out = parse_import_csv(txt, "Default")
    assert out == [
        {"name": "Sol Ring", "anzahl": 1, "edition": "", "album": "Ordner A"},
        {"name": "Llanowar Elves", "anzahl": 3, "edition": "", "album": "Ordner B"},
    ]


def test_parse_no_header_positional():
    txt = "Sol Ring,1,C21,Ordner A\nCounterspell,1,7ED,Ordner B\n"
    out = parse_import_csv(txt, "Default")
    assert [(e["name"], e["album"]) for e in out] == [("Sol Ring", "Ordner A"), ("Counterspell", "Ordner B")]


def test_parse_missing_album_uses_default():
    txt = "Kartenname,Anzahl,Edition\nSol Ring,1,C21\n"
    out = parse_import_csv(txt, "MeinDefault")
    assert out[0]["album"] == "MeinDefault"


def test_parse_empty_and_blank_rows_skipped():
    txt = "Kartenname,Anzahl,Album\nSol Ring,1,A\n\n,,\n"
    out = parse_import_csv(txt, "Default")
    assert len(out) == 1 and out[0]["name"] == "Sol Ring"


# ======================================================================
# 2. End-to-End: mehrere Karten in mehrere Alben, jedes Album nur seine Karten
# ======================================================================
_FAKE_CARDS = {
    "sol ring": {"name": "Sol Ring", "image": "img/sr", "price": "1.20", "type": "Artifact",
                 "colors": [], "cmc": 1, "rarity": "uncommon", "set": "c21", "legalities": {}},
    "lightning bolt": {"name": "Lightning Bolt", "image": "img/lb", "price": "1.50", "type": "Instant",
                       "colors": ["R"], "cmc": 1, "rarity": "common", "set": "m10", "legalities": {}},
    "counterspell": {"name": "Counterspell", "image": "img/cs", "price": "0.80", "type": "Instant",
                     "colors": ["U"], "cmc": 2, "rarity": "common", "set": "7ed", "legalities": {}},
    "llanowar elves": {"name": "Llanowar Elves", "image": "img/le", "price": "0.30", "type": "Creature",
                       "colors": ["G"], "cmc": 1, "rarity": "common", "set": "m12", "legalities": {}},
}


@pytest_asyncio.fixture
async def real_db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    yield session_maker
    await engine.dispose()


def _real_get_db_session(session_maker):
    @asynccontextmanager
    async def _get_db_session():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get_db_session


@pytest.mark.asyncio
async def test_csv_import_multiple_albums_each_returns_own_cards(real_db_session_factory):
    """Der Kern-Regressionstest: 4 Karten in 2 Alben (Semikolon-CSV) importieren,
    dann prüfen, dass jedes Album GENAU seine eigenen Karten liefert -- nicht in
    allen Alben dieselbe (falsche) Karte."""
    session_maker = real_db_session_factory
    user = "importuser"

    csv_text = (
        "Kartenname;Anzahl;Edition;Album\r\n"
        "Sol Ring;1;C21;Ordner A\r\n"
        "Lightning Bolt;2;M10;Ordner A\r\n"
        "Counterspell;1;7ED;Ordner B\r\n"
        "Llanowar Elves;3;M12;Ordner B\r\n"
    )

    fake_fetch = AsyncMock(return_value=_FAKE_CARDS)
    real_db = _real_get_db_session(session_maker)

    with patch("routers.collection.get_db_session", real_db), \
         patch("routers.collection.fetch_card_details_cached", fake_fetch):
        # Import ausführen (Background-Task-Funktion direkt)
        await run_csv_import_task("job-xyz", csv_text, user, "Fallback")

        # 1. get_sammlung: korrekte Gruppierung pro Album
        resp = client.get(f"/api/sammlung/{user}", headers=_auth_headers(user))
        assert resp.status_code == 200
        alben = resp.json()["alben"]
        namen = {a: sorted(k["name"] for k in karten) for a, karten in alben.items()}
        assert namen["Ordner A"] == ["Lightning Bolt", "Lightning Bolt", "Sol Ring"]
        assert namen["Ordner B"] == ["Counterspell", "Llanowar Elves", "Llanowar Elves", "Llanowar Elves"]

        # 2. Filter-Route je Album: nur die eigenen Karten, korrekt getaggt
        for album, erwartet in [
            ("Ordner A", {"Sol Ring", "Lightning Bolt"}),
            ("Ordner B", {"Counterspell", "Llanowar Elves"}),
        ]:
            r = client.get(f"/api/sammlung/{user}/filter", params={"album": album}, headers=_auth_headers(user))
            assert r.status_code == 200
            karten = r.json()["karten"]
            assert {k["name"] for k in karten} == erwartet
            assert all(k["album_name"] == album for k in karten)


@pytest.mark.asyncio
async def test_csv_import_no_cross_album_leak(real_db_session_factory):
    """Ordner B darf NIE eine Karte aus Ordner A enthalten (und umgekehrt)."""
    session_maker = real_db_session_factory
    user = "leakcheck"
    csv_text = "Kartenname,Album\nSol Ring,Ordner A\nCounterspell,Ordner B\n"

    with patch("routers.collection.get_db_session", _real_get_db_session(session_maker)), \
         patch("routers.collection.fetch_card_details_cached", AsyncMock(return_value=_FAKE_CARDS)):
        await run_csv_import_task("job-leak", csv_text, user, "Fallback")

        a = client.get(f"/api/sammlung/{user}/filter", params={"album": "Ordner A"}, headers=_auth_headers(user)).json()["karten"]
        b = client.get(f"/api/sammlung/{user}/filter", params={"album": "Ordner B"}, headers=_auth_headers(user)).json()["karten"]

    assert {k["name"] for k in a} == {"Sol Ring"}
    assert {k["name"] for k in b} == {"Counterspell"}


# ======================================================================
# 3. Garbage-Namen dürfen NIE fuzzy zu fremden Karten werden
# ======================================================================
def test_implausible_names_detected():
    from routers.collection import _is_implausible_card_name
    # Müll (verrutschte Spalten, Set-Codes) -> True
    assert _is_implausible_card_name("1")
    assert _is_implausible_card_name("0.61")
    assert _is_implausible_card_name("SPM")   # löst bei Scryfall fuzzy auf 'Wispmare' auf!
    assert _is_implausible_card_name("ECL")
    assert _is_implausible_card_name("MH2")
    assert _is_implausible_card_name("")
    # Echte (auch kurze) Kartennamen -> False
    assert not _is_implausible_card_name("Opt")
    assert not _is_implausible_card_name("Fog")
    assert not _is_implausible_card_name("Sol Ring")
    assert not _is_implausible_card_name("Plunderprüfer")


@pytest.mark.asyncio
async def test_csv_import_garbage_rows_fail_instead_of_foreign_cards(real_db_session_factory):
    """User-Szenario: Zeilen, deren Namens-Spalte eine Zahl oder ein Set-Code
    ist (verrutschte Spalten), dürfen NICHT per Fuzzy-Match als fremde Karte
    (z.B. 'SPM' -> Wispmare) in den Alben landen. Sie zählen als Fehler; der
    Scryfall-Fetch wird für sie gar nicht erst aufgerufen."""
    from routers import collection as coll

    csv_text = "Kartenname;Anzahl;Edition;Album\nSol Ring;1;C21;Deck A\nSPM;1;;Deck A\n2;1;;Deck B\n"

    requested_names = []

    async def fake_fetch(names):
        requested_names.extend(names)
        # Selbst wenn Scryfall für Müll etwas liefern WÜRDE, darf es nie
        # angefragt werden -- deshalb absichtlich auch 'spm' im Fake-Katalog.
        katalog = dict(_FAKE_CARDS)
        katalog["spm"] = {"name": "Wispmare", "image": "img/wm", "price": "0.10",
                          "type": "Creature", "colors": ["W"], "cmc": 3,
                          "rarity": "common", "set": "lrw", "legalities": {}}
        return {n.lower().strip(): katalog[n.lower().strip()]
                for n in names if n.lower().strip() in katalog}

    session_factory = _real_get_db_session(real_db_session_factory)
    with patch.object(coll, "get_db_session", session_factory), \
         patch.object(coll, "fetch_card_details_cached", side_effect=fake_fetch):
        # Job-Zeile anlegen, damit das Status-Update ins Leere läuft
        async with session_factory() as s:
            await s.execute(text(
                "INSERT INTO import_jobs (job_id, status, erstellt_am) VALUES ('job-g', 'processing', CURRENT_TIMESTAMP)"
            ))
        await coll.run_csv_import_task("job-g", csv_text, "tester", "Import")

        async with session_factory() as s:
            res = await s.execute(text(
                "SELECT karten_name, album_name FROM sammlung_alben WHERE benutzername='tester'"
            ))
            rows = [dict(r) for r in res.mappings().all()]
            res_job = await s.execute(text("SELECT status, result FROM import_jobs WHERE job_id='job-g'"))
            job = res_job.mappings().first()

    # Nur die echte Karte wurde importiert -- KEINE Wispmare, nirgends.
    assert rows == [{"karten_name": "Sol Ring", "album_name": "Deck A"}]
    # Der Müll wurde Scryfall nie vorgelegt
    assert "SPM" not in requested_names and "2" not in requested_names
    # Job-Ergebnis meldet die zwei Fehler ehrlich
    import json as _json
    result = _json.loads(job["result"])
    assert job["status"] == "completed"
    assert result["imported"] == 1
    assert result["failed"] == 2
    assert len(result["errors"]) == 2
