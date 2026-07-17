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

client = TestClient(app)


def _token_for(username: str) -> str:
    return create_access_token({"sub": username})


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {_token_for(username)}"}


@pytest.mark.asyncio
async def test_update_role_requires_authentication():
    """No token at all -> 401, no DB write attempted."""
    response = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "premium"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch('routers.auth.get_db_session')
async def test_user_cannot_self_upgrade_to_premium(mock_get_db):
    """The core exploit this endpoint used to allow: a logged-in free user
    granting themselves premium. Must now be rejected, and no DB write may
    happen."""
    mock_session = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_session

    response = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "premium"},
        headers=_auth_headers("alice"),
    )

    assert response.status_code == 403
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
@patch('routers.auth.get_db_session')
async def test_user_cannot_change_another_users_role(mock_get_db):
    """A logged-in user must not be able to touch someone else's role at all,
    even to downgrade them."""
    mock_session = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_session

    response = client.post(
        "/api/user/update-role",
        json={"benutzername": "bob", "rolle": "free"},
        headers=_auth_headers("alice"),
    )

    assert response.status_code == 403
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
@patch('routers.auth.get_db_session')
async def test_user_can_downgrade_own_role_to_free(mock_get_db):
    """Self-service downgrade (e.g. cancelling a test subscription) is still
    allowed -- only self-upgrade to premium is blocked."""
    mock_session = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_session

    response = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "free"},
        headers=_auth_headers("alice"),
    )

    assert response.status_code == 200
    assert response.json()["erfolg"] is True
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
@patch('routers.auth.get_db_session')
@patch('routers.auth.os.getenv')
async def test_admin_can_grant_premium_to_another_user(mock_getenv, mock_get_db):
    """An explicitly configured admin account is still allowed to grant
    premium to someone else (e.g. manual support case)."""
    mock_getenv.side_effect = lambda key, default=None: (
        "admin_user" if key == "ADMIN_USERNAMES" else default
    )
    mock_session = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_session

    response = client.post(
        "/api/user/update-role",
        json={"benutzername": "bob", "rolle": "premium"},
        headers=_auth_headers("admin_user"),
    )

    assert response.status_code == 200
    assert response.json()["erfolg"] is True
    mock_session.execute.assert_called_once()


# ============================================================================
# End-to-End-Regressionstest: reproduziert genau den "Downgrade-Button
# funktioniert nicht mehr"-Bugreport. Läuft gegen eine echte (in-memory)
# SQLite-Datenbank statt einem Mock, damit bewiesen ist, dass ein eingeloggter
# Premium-Nutzer sich selbst tatsächlich bis in die DB zurückstufen kann --
# nicht nur, dass irgendein UPDATE-Statement aufgerufen wurde.
# ============================================================================
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
async def test_premium_user_can_downgrade_self_end_to_end(real_db_session_factory):
    session_maker = real_db_session_factory

    # Testnutzer als 'premium' anlegen -- exakt der Ausgangszustand des Bugreports.
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES (:name, 'x', 'premium')"),
            {"name": "premium_downgrader"},
        )
        await session.commit()

    with patch('routers.auth.get_db_session', _real_get_db_session(session_maker)):
        response = client.post(
            "/api/user/update-role",
            json={"benutzername": "premium_downgrader", "rolle": "free"},
            headers=_auth_headers("premium_downgrader"),
        )

        assert response.status_code == 200
        assert response.json() == {"erfolg": True, "rolle": "free"}

        # Beweis, dass es wirklich in der DB angekommen ist, nicht nur die
        # HTTP-Antwort stimmt.
        async with session_maker() as session:
            res = await session.execute(
                text("SELECT rolle FROM nutzer WHERE benutzername = :name"),
                {"name": "premium_downgrader"},
            )
            assert res.mappings().first()["rolle"] == "free"
