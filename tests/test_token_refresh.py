"""
tests/test_token_refresh.py – Token-Refresh-Flow (Launch-Blocker #1)

Beweist das geforderte Verhalten: Läuft das Access-Token ab, bleibt der
Nutzer über das Refresh-Token eingeloggt -- ohne erneutes Login.

Zusätzlich abgesichert:
- Ein Refresh-Token wird auf geschützten Endpunkten NICHT als Access-Token
  akzeptiert (type-Claim-Trennung).
- Ein Access-Token kann NICHT als Refresh-Token eingetauscht werden.
- Refresh liest die Rolle frisch aus der DB (Premium-Upgrade kommt im
  nächsten Access-Token an).
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from auth import create_access_token, create_refresh_token, decode_token

client = TestClient(app)


def _mock_db_user(benutzername="alice", rolle="free"):
    """get_db_session-Mock, dessen SELECT einen Nutzer-Row liefert."""
    mock_session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "benutzername": benutzername,
        "rolle": rolle,
    }
    mock_session.execute = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_session


def test_expired_access_token_is_rejected():
    """Vorbedingung des Szenarios: abgelaufenes Access-Token -> 401."""
    expired = create_access_token({"sub": "alice"}, expires_delta=timedelta(seconds=-10))
    resp = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "free"},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


@patch("routers.auth.get_db_session")
def test_refresh_flow_keeps_user_logged_in(mock_get_db):
    """DAS Kernszenario: abgelaufenes Access-Token -> Refresh -> neuer Token
    funktioniert auf einem geschützten Endpoint. Kein Neu-Login nötig."""
    ctx, _ = _mock_db_user("alice", "free")
    mock_get_db.return_value = ctx

    # 1) Access-Token ist abgelaufen -> geschützter Endpoint lehnt ab
    expired = create_access_token({"sub": "alice"}, expires_delta=timedelta(seconds=-10))
    resp = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "free"},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401

    # 2) Refresh-Token eintauschen
    refresh = create_refresh_token({"sub": "alice", "role": "free"})
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    data = resp.json()
    assert data["erfolg"] is True
    assert data["access_token"]
    assert data["refresh_token"]  # Rotation: neues Refresh-Token kommt mit

    # 3) Das neue Access-Token funktioniert auf dem geschützten Endpoint
    resp = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "free"},
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert resp.status_code == 200


@patch("routers.auth.get_db_session")
def test_refresh_returns_fresh_role_from_db(mock_get_db):
    """Rolle kommt aus der DB, nicht aus dem alten Token: User war 'free',
    wurde inzwischen (Webhook) 'premium' -> Refresh liefert 'premium'."""
    ctx, _ = _mock_db_user("alice", "premium")
    mock_get_db.return_value = ctx

    refresh = create_refresh_token({"sub": "alice", "role": "free"})
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rolle"] == "premium"
    assert decode_token(data["access_token"])["role"] == "premium"


def test_access_token_cannot_be_used_as_refresh_token():
    access = create_access_token({"sub": "alice"})
    resp = client.post("/api/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token():
    """Ein 30-Tage-Refresh-Token darf auf geschützten Endpunkten NICHT als
    Access-Token durchgehen."""
    refresh = create_refresh_token({"sub": "alice"})
    resp = client.post(
        "/api/user/update-role",
        json={"benutzername": "alice", "rolle": "free"},
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert resp.status_code == 401


@patch("routers.auth.get_db_session")
def test_refresh_for_deleted_user_is_rejected(mock_get_db):
    mock_session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    mock_get_db.return_value = ctx

    refresh = create_refresh_token({"sub": "gibtsnicht"})
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


def test_garbage_refresh_token_is_rejected():
    resp = client.post("/api/auth/refresh", json={"refresh_token": "kein.echtes.token"})
    assert resp.status_code == 401
