"""
tests/test_subscription_cancel.py – Self-Service-Abo-Kündigung (Launch-Blocker #4)

Die AGB nennen eine Kündigungsfunktion; vorher gab es nur einen Dev-Button,
der die Rolle zurücksetzte, während das Stripe-Abo weiterlief (und weiter
abgebucht hätte). Jetzt: POST /api/checkout/cancel-subscription setzt das
echte Stripe-Abo auf cancel_at_period_end.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from auth import create_access_token

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


def _mock_db_with_subscription(sub_id):
    mock_session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = (
        {"stripe_subscription_id": sub_id} if sub_id is not None else None
    )
    mock_session.execute = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def test_cancel_requires_login():
    resp = client.post("/api/checkout/cancel-subscription")
    assert resp.status_code == 401


@patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"})
@patch("routers.payments.stripe")
@patch("routers.payments.get_db_session")
def test_cancel_without_stripe_subscription_is_honest(mock_db, mock_stripe):
    """Premium ohne Stripe-Abo (Dev-/Admin-Upgrade): ehrliche Meldung,
    KEIN Stripe-Aufruf, keine Schein-Kündigung."""
    mock_db.return_value = _mock_db_with_subscription(None)

    resp = client.post("/api/checkout/cancel-subscription", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["erfolg"] is False
    assert data["kein_abo"] is True
    mock_stripe.Subscription.modify.assert_not_called()


@patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"})
@patch("routers.payments.stripe")
@patch("routers.payments.get_db_session")
def test_cancel_sets_cancel_at_period_end(mock_db, mock_stripe):
    """Kernszenario: Nutzer mit echtem Abo kündigt selbst -- Stripe wird mit
    cancel_at_period_end=True aufgerufen, Antwort nennt das Periodenende.
    Premium wird NICHT sofort entzogen (Downgrade macht der Webhook)."""
    mock_db.return_value = _mock_db_with_subscription("sub_123")
    mock_stripe.Subscription.modify.return_value = {
        "id": "sub_123",
        "cancel_at_period_end": True,
        "current_period_end": 1790000000,
    }

    resp = client.post("/api/checkout/cancel-subscription", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["erfolg"] is True
    assert data["laeuft_bis"] == 1790000000

    mock_stripe.Subscription.modify.assert_called_once_with(
        "sub_123", cancel_at_period_end=True
    )
    # Es darf KEIN Rollen-Downgrade in der DB passiert sein: der einzige
    # DB-Zugriff war das SELECT der Subscription-ID.
    session = mock_db.return_value.__aenter__.return_value
    executed_sql = " ".join(str(c.args[0]) for c in session.execute.call_args_list)
    assert "UPDATE" not in executed_sql.upper()


@patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"})
@patch("routers.payments.stripe")
@patch("routers.payments.get_db_session")
def test_cancel_period_end_from_subscription_items(mock_db, mock_stripe):
    """Neuere Stripe-API-Versionen liefern current_period_end auf den Items."""
    mock_db.return_value = _mock_db_with_subscription("sub_456")
    mock_stripe.Subscription.modify.return_value = {
        "id": "sub_456",
        "cancel_at_period_end": True,
        "items": {"data": [{"current_period_end": 1795000000}]},
    }

    resp = client.post("/api/checkout/cancel-subscription", headers=_auth_headers("bob"))
    assert resp.json()["laeuft_bis"] == 1795000000


@patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"})
@patch("routers.payments.stripe")
@patch("routers.payments.get_db_session")
def test_cancel_stripe_error_is_reported(mock_db, mock_stripe):
    mock_db.return_value = _mock_db_with_subscription("sub_789")
    mock_stripe.Subscription.modify.side_effect = Exception("No such subscription")

    resp = client.post("/api/checkout/cancel-subscription", headers=_auth_headers("carol"))
    data = resp.json()
    assert data["erfolg"] is False
    assert "fehlgeschlagen" in data["error"]
