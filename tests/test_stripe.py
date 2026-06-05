import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from main import app

os.environ["DEV_MODE"] = "True"
client = TestClient(app)

@pytest.mark.asyncio
@patch('routers.payments.get_db_session')
async def test_stripe_webhook_checkout_session_completed(mock_get_db):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_db

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_test_12345",
                "metadata": {
                    "benutzername": "premium_user"
                }
            }
        }
    }

    # Simulate webhook post without signature (which uses construct_from)
    response = client.post("/api/checkout/webhook", json=payload)
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

    payload = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_test_12345"
            }
        }
    }

    response = client.post("/api/checkout/webhook", json=payload)
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

    payload = {
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "customer": "cus_test_12345"
            }
        }
    }

    response = client.post("/api/checkout/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_db.execute.assert_called_once()
    sql_arg = mock_db.execute.call_args[0][0].text
    params_arg = mock_db.execute.call_args[0][1]
    assert "UPDATE nutzer SET rolle='free'" in sql_arg
    assert params_arg["cust_id"] == "cus_test_12345"
