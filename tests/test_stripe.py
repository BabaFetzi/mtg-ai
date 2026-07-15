import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from main import app

client = TestClient(app)

TEST_WEBHOOK_SECRET = "whsec_test_secret_for_unit_tests"


def _sign(payload_bytes: bytes, secret: str = TEST_WEBHOOK_SECRET, timestamp: int = None) -> str:
    """Builds a Stripe-compatible `Stripe-Signature` header using Stripe's
    documented scheme: t=<timestamp>,v1=hmac_sha256(secret, "<timestamp>.<payload>")."""
    timestamp = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{timestamp}.{payload_bytes.decode('utf-8')}"
    signature = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _payload(event_type: str, obj: dict) -> bytes:
    # A real Stripe event envelope -- stripe.Webhook.construct_event (unlike
    # the old, laxer stripe.Event.construct_from bypass) requires the
    # top-level "object": "event" field to be present.
    return json.dumps({
        "id": "evt_test_123",
        "object": "event",
        "type": event_type,
        "data": {"object": obj},
    }).encode("utf-8")


@pytest.fixture(autouse=True)
def _webhook_env(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)
    # A stray DEV_MODE=True must NOT bring back the old unsigned-webhook bypass.
    monkeypatch.setenv("DEV_MODE", "True")
    yield


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_stripe_webhook_checkout_session_completed(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    body = _payload("checkout.session.completed", {
        "customer": "cus_test_12345",
        "metadata": {"benutzername": "premium_user"},
    })
    response = client.post(
        "/api/checkout/webhook",
        content=body,
        headers={"stripe-signature": _sign(body), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_db.execute.assert_called_once()
    sql_arg = mock_db.execute.call_args[0][0].text
    params_arg = mock_db.execute.call_args[0][1]
    assert "UPDATE nutzer SET rolle='premium'" in sql_arg
    assert params_arg["cust_id"] == "cus_test_12345"
    assert params_arg["name"] == "premium_user"


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_stripe_webhook_subscription_deleted(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    body = _payload("customer.subscription.deleted", {"customer": "cus_test_12345"})
    response = client.post(
        "/api/checkout/webhook",
        content=body,
        headers={"stripe-signature": _sign(body), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_db.execute.assert_called_once()
    sql_arg = mock_db.execute.call_args[0][0].text
    params_arg = mock_db.execute.call_args[0][1]
    assert "UPDATE nutzer SET rolle='free'" in sql_arg
    assert params_arg["cust_id"] == "cus_test_12345"


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_stripe_webhook_invoice_payment_failed(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    body = _payload("invoice.payment_failed", {"customer": "cus_test_12345"})
    response = client.post(
        "/api/checkout/webhook",
        content=body,
        headers={"stripe-signature": _sign(body), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_db.execute.assert_called_once()
    sql_arg = mock_db.execute.call_args[0][0].text
    params_arg = mock_db.execute.call_args[0][1]
    assert "UPDATE nutzer SET rolle='free'" in sql_arg
    assert params_arg["cust_id"] == "cus_test_12345"


# ============================================================================
# Regression tests for the closed vulnerability: the old code accepted
# completely unsigned webhook payloads whenever DEV_MODE=True, so anyone who
# knew (or guessed) that flag was set in an environment could POST a forged
# "checkout.session.completed" event and grant themselves free premium.
# DEV_MODE=True is set via the autouse fixture above for every test in this
# file, so these two prove it no longer has any effect on signature checking.
# ============================================================================
@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_webhook_rejects_missing_signature_even_with_dev_mode_true(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    body = _payload("checkout.session.completed", {
        "customer": "cus_attacker",
        "metadata": {"benutzername": "attacker"},
    })
    # No stripe-signature header -- the old DEV_MODE branch would have
    # accepted this via stripe.Event.construct_from() and granted premium.
    response = client.post("/api/checkout/webhook", content=body, headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_webhook_rejects_forged_signature_even_with_dev_mode_true(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    body = _payload("checkout.session.completed", {
        "customer": "cus_attacker",
        "metadata": {"benutzername": "attacker"},
    })
    forged_signature = _sign(body, secret="whsec_not_the_real_secret")
    response = client.post(
        "/api/checkout/webhook",
        content=body,
        headers={"stripe-signature": forged_signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    mock_db.execute.assert_not_called()
