"""
tests/test_register.py – Registrierung mit E-Mail (T-1.1)

Prüft gegen das echte Schema, dass /api/register die E-Mail erfasst,
das Format validiert und doppelte E-Mails/Benutzernamen ablehnt.
"""

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from main import app
from database import Base

client = TestClient(app)


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
async def test_register_stores_email(real_db_session_factory):
    with patch('routers.auth.get_db_session', _real_get_db_session(real_db_session_factory)):
        resp = client.post("/api/register", json={
            "benutzername": "neuling",
            "passwort": "geheim123",
            "email": "Neuling@Example.COM",
        })
        assert resp.status_code == 200
        assert resp.json().get("erfolg") is True

        # E-Mail wurde normalisiert (lowercase) gespeichert.
        async with real_db_session_factory() as session:
            row = (await session.execute(
                text("SELECT email FROM nutzer WHERE benutzername = :n"),
                {"n": "neuling"},
            )).mappings().first()
        assert row is not None
        assert row["email"] == "neuling@example.com"


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(real_db_session_factory):
    with patch('routers.auth.get_db_session', _real_get_db_session(real_db_session_factory)):
        resp = client.post("/api/register", json={
            "benutzername": "wer",
            "passwort": "geheim123",
            "email": "keine-echte-email",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("erfolg") is False
        assert "mail" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(real_db_session_factory):
    with patch('routers.auth.get_db_session', _real_get_db_session(real_db_session_factory)):
        first = client.post("/api/register", json={
            "benutzername": "erster",
            "passwort": "geheim123",
            "email": "dup@example.com",
        })
        assert first.json().get("erfolg") is True

        second = client.post("/api/register", json={
            "benutzername": "zweiter",
            "passwort": "geheim123",
            "email": "dup@example.com",
        })
        body = second.json()
        assert body.get("erfolg") is False
        assert "mail" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_register_requires_email_field():
    # Fehlt die E-Mail komplett, greift die Pydantic-Validierung (422).
    resp = client.post("/api/register", json={
        "benutzername": "ohnemail",
        "passwort": "geheim123",
    })
    assert resp.status_code == 422
