import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app
from auth import create_access_token

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
