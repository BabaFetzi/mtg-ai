import pytest
from unittest.mock import MagicMock, patch

import routers.cards


@pytest.mark.asyncio
async def test_translate_oracle_text_free_user_no_gemini_call():
    with patch('services.ai_service.model_lite') as mock_model_lite:
        result = await routers.cards._translate_oracle_text("Flying, vigilance.", is_premium=False, benutzername="free_user")
        mock_model_lite.generate_content.assert_not_called()
        assert "Premium-Feature" in result
        assert "Flying, vigilance." in result


@patch('routers.cards.check_and_increment_ai_usage')
@patch('services.ai_service.model_lite')
@pytest.mark.asyncio
async def test_translate_oracle_text_premium_uses_model_lite(mock_model_lite, mock_usage):
    """Regressionstest fürs Modell-Tiering: Kartenübersetzung muss über
    model_lite laufen, nicht über das teurere model (Gemini 2.5 Flash)."""
    mock_usage.return_value = True
    mock_response = MagicMock()
    mock_response.text = "Fliegend, Wachsamkeit."
    mock_model_lite.generate_content.return_value = mock_response

    result = await routers.cards._translate_oracle_text("Flying, vigilance.", is_premium=True, benutzername="premium_user")

    assert result == "Fliegend, Wachsamkeit."
    mock_model_lite.generate_content.assert_called_once()
    mock_usage.assert_called_once_with("premium_user")


@patch('routers.cards.check_and_increment_ai_usage')
@patch('services.ai_service.model_lite')
@pytest.mark.asyncio
async def test_translate_oracle_text_blocked_when_monthly_limit_reached(mock_model_lite, mock_usage):
    """Regressionstest fürs Monatslimit: ist es erreicht, wird Gemini nicht
    aufgerufen -- der Originaltext wird stattdessen zurückgegeben."""
    mock_usage.return_value = False

    result = await routers.cards._translate_oracle_text("Flying, vigilance.", is_premium=True, benutzername="power_user")

    mock_model_lite.generate_content.assert_not_called()
    assert "Originaltext (Englisch)" in result
    assert "Flying, vigilance." in result


@pytest.mark.asyncio
async def test_translate_oracle_text_empty_input():
    assert await routers.cards._translate_oracle_text("", is_premium=True, benutzername="x") == "Keine Textbeschreibung vorhanden."
