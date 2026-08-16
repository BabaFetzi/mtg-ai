import time
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from auth import (
    hash_passwort,
    verify_passwort,
    create_access_token,
    create_refresh_token,
    decode_token,
    check_login_rate_limit,
    record_login_attempt,
    MAX_LOGIN_ATTEMPTS,
)


def test_password_hashing():
    pw = "SuperSecurePassword123"
    hashed = hash_passwort(pw)
    assert hashed != pw
    assert verify_passwort(pw, hashed) is True
    assert verify_passwort("WrongPassword", hashed) is False


def test_jwt_generation_and_decoding():
    data = {"sub": "testuser", "role": "premium"}

    # Access token
    token = create_access_token(data)
    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "testuser"
    assert decoded["role"] == "premium"
    assert "exp" in decoded

    # Expired token
    expired_token = create_access_token(data, expires_delta=timedelta(seconds=-10))
    assert decode_token(expired_token) is None

    # Refresh token
    refresh_token = create_refresh_token(data)
    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh is not None
    assert decoded_refresh["sub"] == "testuser"


# ======================================================================
# Brute-Force-Schutz
# ======================================================================
# Der Zähler lag früher in einem Dictionary im Modul auth. Damit hatte jeder
# uvicorn-Worker seinen eigenen -- aus 5 erlaubten Fehlversuchen wurden bei 2
# Workern faktisch 10 -- und ein Neustart löschte alle Sperren. Er liegt jetzt
# in der Datenbank, und diese Tests laufen deshalb gegen eine echte.

@pytest_asyncio.fixture
async def anmelde_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _sitzung():
        async with macher() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    with patch("database.get_db_session", _sitzung):
        yield macher
    await engine.dispose()


async def _bis_zur_sperre(ip: str, user: str) -> None:
    for _ in range(MAX_LOGIN_ATTEMPTS):
        try:
            await record_login_attempt(ip, user, erfolg=False)
        except HTTPException:
            pass


@pytest.mark.asyncio
async def test_login_rate_limiting(anmelde_db):
    ip, user = "192.168.1.1", "hacker"

    # Die ersten vier Fehlversuche sperren noch nicht.
    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        await record_login_attempt(ip, user, erfolg=False)
        await check_login_rate_limit(ip, user)

    # Der fünfte löst die Sperre aus.
    with pytest.raises(HTTPException) as exc_info:
        await record_login_attempt(ip, user, erfolg=False)
    assert exc_info.value.status_code == 429
    assert "gesperrt" in exc_info.value.detail

    # Danach ist auch die blosse Prüfung gesperrt.
    with pytest.raises(HTTPException) as exc_info:
        await check_login_rate_limit(ip, user)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_erfolgreiche_anmeldung_loescht_den_zaehler(anmelde_db):
    ip, user = "192.168.1.2", "rueckkehrer"
    for _ in range(3):
        await record_login_attempt(ip, user, erfolg=False)

    await record_login_attempt(ip, user, erfolg=True)

    # Nach dem Erfolg steht das volle Kontingent wieder zur Verfügung.
    assert await record_login_attempt(ip, user, erfolg=False) == MAX_LOGIN_ATTEMPTS - 1


@pytest.mark.asyncio
async def test_login_attempts_warn_before_lockout(anmelde_db):
    """Vor der 15-Minuten-Sperre muss gewarnt werden, statt den Nutzer
    unangekündigt auszusperren."""
    ip, user = "10.0.0.99", "warnuser"

    verbleibend = [await record_login_attempt(ip, user, erfolg=False)
                   for _ in range(MAX_LOGIN_ATTEMPTS - 1)]

    # Streng absteigend bis 1 -- der letzte Fehlversuch vor der Sperre.
    assert verbleibend == list(range(MAX_LOGIN_ATTEMPTS - 1, 0, -1))

    with pytest.raises(HTTPException) as exc:
        await record_login_attempt(ip, user, erfolg=False)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_sperre_ueberlebt_prozessgrenzen(anmelde_db):
    """Der eigentliche Grund für die Umstellung.

    Vorher lag der Zähler im Prozessspeicher: jeder Worker hatte sein eigenes
    Kontingent, und ein Neustart löschte alle Sperren -- ein Angreifer musste
    nur auf das nächste Deployment warten.
    """
    import importlib
    import services.anmeldeversuche as av

    ip, user = "10.0.0.50", "hartnaeckig"
    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        await record_login_attempt(ip, user, erfolg=False)

    # Modul neu laden = frischer Prozessspeicher, wie ein zweiter Worker.
    importlib.reload(av)

    with pytest.raises(HTTPException) as exc:
        await av.merken(ip, user, erfolg=False)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_andere_nutzer_bleiben_unberuehrt(anmelde_db):
    ip = "10.0.0.51"
    await _bis_zur_sperre(ip, "opfer")

    # Dieselbe IP, anderer Name -- eigenes Kontingent.
    await check_login_rate_limit(ip, "jemand_anders")


@pytest.mark.asyncio
async def test_lockout_message_is_in_minutes_not_raw_seconds(anmelde_db):
    """Die Wartezeit wird in Minuten kommuniziert (nicht '843 Sekunden')."""
    ip, user = "10.0.0.98", "blockeduser"
    await _bis_zur_sperre(ip, user)

    with pytest.raises(HTTPException) as exc:
        await check_login_rate_limit(ip, user)
    assert "Minute" in exc.value.detail
    assert "Sekunden" not in exc.value.detail


@pytest.mark.asyncio
async def test_abgelaufene_eintraege_werden_aufgeraeumt(anmelde_db):
    import services.anmeldeversuche as av

    await record_login_attempt("10.0.0.52", "alt", erfolg=False)
    async with anmelde_db() as s:
        await s.execute(
            text("UPDATE anmeldeversuche SET zuletzt = :alt WHERE benutzername = 'alt'"),
            {"alt": time.time() - av.VERFALL_SEKUNDEN - 60})
        await s.commit()

    assert await av.aufraeumen() == 1


@pytest.mark.asyncio
async def test_laufende_sperre_wird_nicht_weggeraeumt(anmelde_db):
    """Sonst wäre eine Sperre nach dem nächsten Wartungslauf einfach weg."""
    import services.anmeldeversuche as av

    ip, user = "10.0.0.53", "gesperrt"
    await _bis_zur_sperre(ip, user)
    async with anmelde_db() as s:
        await s.execute(
            text("UPDATE anmeldeversuche SET zuletzt = :alt WHERE benutzername = :b"),
            {"alt": time.time() - av.VERFALL_SEKUNDEN - 60, "b": user})
        await s.commit()

    assert await av.aufraeumen() == 0
    with pytest.raises(HTTPException):
        await check_login_rate_limit(ip, user)
