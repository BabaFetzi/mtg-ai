"""tests/test_passwort_reset.py – Passwort vergessen und zurücksetzen

Bis zu diesem Punkt gab es keinen Weg zurück ins eigene Konto: Wer sein
Passwort verlor, verlor seine Sammlung. Bei einem Bezahlprodukt ist das ein
garantierter Supportfall.

Die Tests laufen gegen eine echte (In-Memory-)SQLite-Datenbank, nicht gegen
Mocks -- sonst würde ein Fehler im SQL erst im Betrieb auffallen.
"""

import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from main import app
from auth import verify_passwort
from database import Base

client = TestClient(app)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, expire_on_commit=False)
    async with macher() as s:
        await s.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle, email) "
                 "VALUES ('anna', 'altes-hash', 'free', 'anna@example.invalid')")
        )
        await s.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle, email) "
                 "VALUES ('ohne_mail', 'altes-hash', 'free', NULL)")
        )
        await s.commit()
    yield macher
    await engine.dispose()


def _session_fabrik(macher):
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


class MailFang:
    """Fängt Mails ab, statt sie zu verschicken."""
    def __init__(self):
        self.mails = []

    def __call__(self, empfaenger, betreff, text, html=None):
        self.mails.append({"an": empfaenger, "betreff": betreff, "text": text})

    def link(self):
        import re
        treffer = re.search(r"token=([\w\-]+)", self.mails[-1]["text"])
        return treffer.group(1) if treffer else None


@pytest.fixture
def post(db):
    fang = MailFang()

    def _post(pfad, nutzlast):
        with patch("routers.auth.get_db_session", _session_fabrik(db)), \
             patch("services.mailer.sende_mail", fang):
            return client.post(pfad, json=nutzlast)

    _post.fang = fang
    return _post


# ----------------------------------------------------------------------
# Der glückliche Pfad
# ----------------------------------------------------------------------
def test_kompletter_ablauf_mit_benutzername(post, db):
    antwort = post("/api/passwort/vergessen", {"kennung": "anna"})
    assert antwort.status_code == 200
    assert antwort.json()["erfolg"] is True
    assert len(post.fang.mails) == 1
    assert post.fang.mails[0]["an"] == "anna@example.invalid"

    token = post.fang.link()
    assert token, "Die Mail muss einen Token-Link enthalten"

    neu = post("/api/passwort/zuruecksetzen", {"token": token, "neues_passwort": "NeuesGeheim123"})
    assert neu.status_code == 200, neu.text
    assert neu.json()["erfolg"] is True


def test_auch_ueber_die_email_adresse_anforderbar(post):
    post("/api/passwort/vergessen", {"kennung": "ANNA@example.invalid"})
    assert len(post.fang.mails) == 1, "Gross-/Kleinschreibung darf nicht stören"


@pytest.mark.asyncio
async def test_neues_passwort_landet_wirklich_in_der_datenbank(post, db):
    post("/api/passwort/vergessen", {"kennung": "anna"})
    token = post.fang.link()
    post("/api/passwort/zuruecksetzen", {"token": token, "neues_passwort": "NeuesGeheim123"})

    async with db() as s:
        res = await s.execute(text("SELECT passwort_hash FROM nutzer WHERE benutzername='anna'"))
        gespeichert = res.mappings().first()["passwort_hash"]

    assert gespeichert != "altes-hash"
    assert verify_passwort("NeuesGeheim123", gespeichert), "Das neue Passwort muss passen"
    assert not verify_passwort("altes-hash", gespeichert)


@pytest.mark.asyncio
async def test_bestehende_sitzungen_werden_beendet(post, db):
    """Wer sein Passwort zurücksetzt, will meist auch fremde Sitzungen los."""
    async with db() as s:
        await s.execute(text(
            "INSERT INTO sessions (id, benutzername, refresh_token, laeuft_ab) "
            "VALUES ('s1', 'anna', 'irgendein-refresh', :ablauf)"),
            {"ablauf": datetime.utcnow() + timedelta(days=30)})
        await s.commit()

    post("/api/passwort/vergessen", {"kennung": "anna"})
    post("/api/passwort/zuruecksetzen", {"token": post.fang.link(), "neues_passwort": "NeuesGeheim123"})

    async with db() as s:
        res = await s.execute(text("SELECT COUNT(*) AS n FROM sessions WHERE benutzername='anna'"))
        assert res.mappings().first()["n"] == 0


# ----------------------------------------------------------------------
# Sicherheitseigenschaften
# ----------------------------------------------------------------------
def test_unbekannte_kennung_sieht_genauso_aus(post):
    """Sonst wird "Passwort vergessen" zum Werkzeug, um gültige Konten
    durchzuprobieren."""
    bekannt = post("/api/passwort/vergessen", {"kennung": "anna"})
    post.fang.mails.clear()
    unbekannt = post("/api/passwort/vergessen", {"kennung": "gibtesnicht"})

    assert bekannt.status_code == unbekannt.status_code == 200
    assert bekannt.json() == unbekannt.json(), "Die Antworten müssen identisch sein"
    assert post.fang.mails == [], "An ein nicht existierendes Konto darf nichts rausgehen"


def test_konto_ohne_email_verraet_sich_nicht(post):
    antwort = post("/api/passwort/vergessen", {"kennung": "ohne_mail"})
    assert antwort.status_code == 200
    assert antwort.json()["erfolg"] is True
    assert post.fang.mails == []


@pytest.mark.asyncio
async def test_token_steht_nur_als_hash_in_der_datenbank(post, db):
    post("/api/passwort/vergessen", {"kennung": "anna"})
    token = post.fang.link()

    async with db() as s:
        res = await s.execute(text("SELECT token_hash FROM passwort_resets"))
        gespeichert = [z["token_hash"] for z in res.mappings().all()]

    assert token not in gespeichert, "Das rohe Token darf nicht in der DB stehen"
    assert hashlib.sha256(token.encode()).hexdigest() in gespeichert


def test_token_funktioniert_nur_einmal(post):
    post("/api/passwort/vergessen", {"kennung": "anna"})
    token = post.fang.link()

    erst = post("/api/passwort/zuruecksetzen", {"token": token, "neues_passwort": "NeuesGeheim123"})
    zweit = post("/api/passwort/zuruecksetzen", {"token": token, "neues_passwort": "NochEinAnderes9"})

    assert erst.status_code == 200
    assert zweit.status_code == 400
    assert "nicht mehr gültig" in zweit.json()["detail"]


def test_neue_anforderung_entwertet_die_alte(post):
    """Es soll immer nur ein gültiger Link im Umlauf sein."""
    post("/api/passwort/vergessen", {"kennung": "anna"})
    alt = post.fang.link()
    post("/api/passwort/vergessen", {"kennung": "anna"})
    neu = post.fang.link()

    assert alt != neu
    assert post("/api/passwort/zuruecksetzen", {"token": alt, "neues_passwort": "NeuesGeheim123"}).status_code == 400
    assert post("/api/passwort/zuruecksetzen", {"token": neu, "neues_passwort": "NeuesGeheim123"}).status_code == 200


@pytest.mark.asyncio
async def test_abgelaufenes_token_wird_abgelehnt(post, db):
    post("/api/passwort/vergessen", {"kennung": "anna"})
    token = post.fang.link()

    async with db() as s:
        await s.execute(text("UPDATE passwort_resets SET laeuft_ab = :vorher"),
                        {"vorher": datetime.utcnow() - timedelta(minutes=1)})
        await s.commit()

    antwort = post("/api/passwort/zuruecksetzen", {"token": token, "neues_passwort": "NeuesGeheim123"})
    assert antwort.status_code == 400


def test_erfundenes_token_wird_abgelehnt(post):
    antwort = post("/api/passwort/zuruecksetzen",
                   {"token": "voellig-ausgedacht", "neues_passwort": "NeuesGeheim123"})
    assert antwort.status_code == 400


def test_zu_kurzes_passwort_wird_abgelehnt(post):
    post("/api/passwort/vergessen", {"kennung": "anna"})
    antwort = post("/api/passwort/zuruecksetzen", {"token": post.fang.link(), "neues_passwort": "kurz"})
    assert antwort.status_code == 400
    assert "mindestens" in antwort.json()["detail"]


def test_scheiternder_mailversand_verraet_das_konto_nicht(db):
    """Auch wenn die Mail nicht rausgeht, muss die Antwort gleich aussehen."""
    from services.mailer import MailVersandFehler

    def kaputt(*a, **kw):
        raise MailVersandFehler("SMTP nicht erreichbar")

    with patch("routers.auth.get_db_session", _session_fabrik(db)), \
         patch("services.mailer.sende_mail", kaputt):
        antwort = client.post("/api/passwort/vergessen", json={"kennung": "anna"})

    assert antwort.status_code == 200
    assert antwort.json()["erfolg"] is True
