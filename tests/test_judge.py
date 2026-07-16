import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from main import app

client = TestClient(app)


@pytest.mark.asyncio
@patch('routers.ai.check_user_premium')
async def test_judge_free_paywall(mock_check_premium):
    mock_check_premium.return_value = False
    response = client.post("/api/judge", json={"frage": "Was ist Trample?", "benutzername": "free_user"})
    assert response.status_code == 200
    assert "PAYWALL" in response.json()["antwort"]


@pytest.mark.asyncio
@patch('routers.ai.check_user_premium')
@patch('routers.ai.check_and_increment_ai_usage')
@patch('routers.ai.model_lite')
async def test_judge_premium_uses_model_lite(mock_model_lite, mock_usage, mock_check_premium):
    """Regressionstest fürs Modell-Tiering: Judge muss über model_lite laufen,
    nicht über das teurere model (Gemini 2.5 Flash)."""
    mock_check_premium.return_value = True
    mock_usage.return_value = True
    mock_response = MagicMock()
    mock_response.text = "Trample lässt überschüssigen Kampfschaden zum Gegner durchgehen."
    mock_model_lite.generate_content.return_value = mock_response

    response = client.post("/api/judge", json={"frage": "Was ist Trample?", "benutzername": "premium_user"})

    assert response.status_code == 200
    assert "Trample" in response.json()["antwort"]
    mock_model_lite.generate_content.assert_called_once()
    mock_usage.assert_called_once_with("premium_user")


@pytest.mark.asyncio
@patch('routers.ai.check_user_premium')
@patch('routers.ai.check_and_increment_ai_usage')
@patch('routers.ai.model_lite')
async def test_judge_blocked_when_monthly_limit_reached(mock_model_lite, mock_usage, mock_check_premium):
    """Regressionstest fürs Monatslimit: ist es erreicht, wird Gemini gar
    nicht erst aufgerufen -- das war vorher unbegrenzt möglich."""
    mock_check_premium.return_value = True
    mock_usage.return_value = False

    response = client.post("/api/judge", json={"frage": "Was ist Trample?", "benutzername": "power_user"})

    assert response.status_code == 200
    assert "Limit" in response.json()["antwort"]
    mock_model_lite.generate_content.assert_not_called()
