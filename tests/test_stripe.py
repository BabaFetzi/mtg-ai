import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from auth import create_access_token

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

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


# ============================================================================
# Regressionstests: create_checkout_session las vorher os.getenv("STRIPE_API_KEY"),
# obwohl die Env-Var überall sonst (und in der .env) STRIPE_SECRET_KEY heisst --
# dadurch griff IMMER der simulierte Fallback, selbst mit korrekt gesetztem
# Secret Key. Diese Tests beweisen, dass der richtige Name jetzt gelesen wird
# und eine echte Checkout-Session entsteht, statt der Simulation.
# ============================================================================
@pytest.mark.asyncio
async def test_create_checkout_session_uses_stripe_secret_key_env_var(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_dummy")

    fake_session = MagicMock()
    fake_session.url = "https://checkout.stripe.com/c/pay/cs_test_dummy"

    with patch('stripe.checkout.Session.create', return_value=fake_session) as mock_create:
        response = client.post(
            "/api/checkout/create-session",
            json={"benutzername": "testuser", "host_url": "http://localhost:5175"},
            headers=_auth_headers("testuser"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["erfolg"] is True
    assert data["simulated"] is False
    assert data["url"] == "https://checkout.stripe.com/c/pay/cs_test_dummy"
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["line_items"][0]["price"] == "price_dummy"


@pytest.mark.asyncio
async def test_create_checkout_session_falls_back_to_simulated_without_price_id(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)

    with patch('stripe.checkout.Session.create') as mock_create:
        response = client.post(
            "/api/checkout/create-session",
            json={"benutzername": "testuser", "host_url": "http://localhost:5175"},
            headers=_auth_headers("testuser"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["simulated"] is True
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_create_checkout_session_falls_back_to_simulated_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_dummy")

    response = client.post(
        "/api/checkout/create-session",
        json={"benutzername": "testuser", "host_url": "http://localhost:5175"},
        headers=_auth_headers("testuser"),
    )

    assert response.status_code == 200
    assert response.json()["simulated"] is True


# ============================================================================
# GET /api/checkout/price -- ersetzt den fest einprogrammierten Frontend-Preis.
# ============================================================================
@pytest.mark.asyncio
async def test_checkout_price_returns_live_stripe_price(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_dummy")

    fake_price = MagicMock()
    fake_price.unit_amount = 390
    fake_price.currency = "chf"
    fake_price.recurring.interval = "month"

    with patch('stripe.Price.retrieve', return_value=fake_price):
        response = client.get("/api/checkout/price")

    assert response.status_code == 200
    data = response.json()
    assert data["konfiguriert"] is True
    assert data["betrag"] == 3.90
    assert data["waehrung"] == "CHF"
    assert data["intervall"] == "month"


@pytest.mark.asyncio
async def test_checkout_price_not_configured_without_price_id(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.delenv("PREMIUM_PRICE_DISPLAY", raising=False)

    response = client.get("/api/checkout/price")

    assert response.status_code == 200
    assert response.json() == {"konfiguriert": False}


@pytest.mark.asyncio
async def test_checkout_price_uses_env_fallback_when_stripe_price_missing(monkeypatch):
    """Ohne STRIPE_PRICE_ID, aber mit gesetztem operator-Fallback PREMIUM_PRICE_DISPLAY
    zeigt die Preisseite einen echten Preis statt 'nicht verfügbar'."""
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.setenv("PREMIUM_PRICE_DISPLAY", "3.90")
    monkeypatch.setenv("PREMIUM_CURRENCY", "chf")

    response = client.get("/api/checkout/price")

    assert response.status_code == 200
    data = response.json()
    assert data["konfiguriert"] is True
    assert data["betrag"] == 3.90
    assert data["waehrung"] == "CHF"
    assert data["quelle"] == "fallback"


@pytest.mark.asyncio
async def test_checkout_price_fallback_handles_comma_decimal(monkeypatch):
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.setenv("PREMIUM_PRICE_DISPLAY", "4,50")

    response = client.get("/api/checkout/price")

    assert response.json()["betrag"] == 4.50


# ======================================================================
# verify-session (T-8.3): serverseitige Bestätigung als Webhook-Fallback
# ======================================================================
@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_verify_session_grants_premium_when_paid_and_owned(mock_get_db, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    fake_session = {
        "payment_status": "paid",
        "status": "complete",
        "customer": "cus_abc",
        "subscription": "sub_abc",
        "metadata": {"benutzername": "premium_user"},
    }
    with patch("routers.payments.stripe.checkout.Session.retrieve", return_value=fake_session):
        resp = client.post(
            "/api/checkout/verify-session",
            json={"session_id": "cs_test_123"},
            headers=_auth_headers("premium_user"),
        )
    assert resp.status_code == 200
    assert resp.json()["erfolg"] is True
    sql_arg = mock_db.execute.call_args[0][0].text
    assert "UPDATE nutzer SET rolle='premium'" in sql_arg
    assert mock_db.execute.call_args[0][1]["name"] == "premium_user"


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_verify_session_rejects_foreign_session(mock_get_db, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    fake_session = {
        "payment_status": "paid",
        "status": "complete",
        "metadata": {"benutzername": "someone_else"},
    }
    with patch("routers.payments.stripe.checkout.Session.retrieve", return_value=fake_session):
        resp = client.post(
            "/api/checkout/verify-session",
            json={"session_id": "cs_test_123"},
            headers=_auth_headers("attacker"),
        )
    assert resp.status_code == 200
    assert resp.json()["erfolg"] is False
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_verify_session_rejects_unpaid(mock_get_db, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    fake_session = {
        "payment_status": "unpaid",
        "status": "open",
        "metadata": {"benutzername": "premium_user"},
    }
    with patch("routers.payments.stripe.checkout.Session.retrieve", return_value=fake_session):
        resp = client.post(
            "/api/checkout/verify-session",
            json={"session_id": "cs_test_123"},
            headers=_auth_headers("premium_user"),
        )
    assert resp.status_code == 200
    assert resp.json()["erfolg"] is False
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_verify_session_requires_auth():
    resp = client.post("/api/checkout/verify-session", json={"session_id": "cs_test_123"})
    assert resp.status_code == 401
