import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from main import app

client = TestClient(app)

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
@patch('routers.decks.get_db_session')
async def test_create_deck_premium(mock_get_db, mock_check_premium):
    mock_check_premium.return_value = True
    
    mock_session = AsyncMock()
    mock_get_db.return_value.__aenter__.return_value = mock_session
    
    payload = {
        "benutzername": "premium_user",
        "deck_name": "Pro Deck",
        "deck_liste": "1 Sol Ring"
    }
    
    response = client.post("/api/decks/erstellen", json=payload)
    assert response.status_code == 200
    assert response.json()["erfolg"] is True
    
    # Check that INSERT was executed
    assert mock_session.execute.call_count == 1
    sql = mock_session.execute.call_args[0][0].text
    assert "INSERT INTO decks" in sql

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
@patch('routers.decks.get_db_session')
async def test_create_deck_free_under_limit(mock_get_db, mock_check_premium):
    mock_check_premium.return_value = False
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 2  # Has 2 decks
    mock_session.execute.return_value = mock_result
    mock_get_db.return_value.__aenter__.return_value = mock_session
    
    payload = {
        "benutzername": "free_user",
        "deck_name": "Third Deck",
        "deck_liste": "1 Sol Ring"
    }
    
    response = client.post("/api/decks/erstellen", json=payload)
    assert response.status_code == 200
    assert response.json()["erfolg"] is True
    
    # Check SELECT COUNT and then INSERT were executed
    assert mock_session.execute.call_count == 2

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
@patch('routers.decks.get_db_session')
async def test_create_deck_free_limit_reached(mock_get_db, mock_check_premium):
    mock_check_premium.return_value = False
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3  # Has 3 decks
    mock_session.execute.return_value = mock_result
    mock_get_db.return_value.__aenter__.return_value = mock_session
    
    payload = {
        "benutzername": "free_user",
        "deck_name": "Fourth Deck",
        "deck_liste": "1 Sol Ring"
    }
    
    response = client.post("/api/decks/erstellen", json=payload)
    assert response.status_code == 403
    assert "Limit erreicht" in response.json()["detail"]
    
    # Only select count was executed, no INSERT
    assert mock_session.execute.call_count == 1
    sql = mock_session.execute.call_args[0][0].text
    assert "SELECT COUNT(*)" in sql

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_deck_roast_free_paywall(mock_check_premium):
    mock_check_premium.return_value = False
    payload = {
        "benutzername": "free_user",
        "deck_liste": "1 Sol Ring",
        "format": "commander"
    }
    response = client.post("/api/deck/roast", json=payload)
    assert response.status_code == 200
    assert response.json()["error"] == "paywall"

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
@patch('routers.decks.model')
async def test_deck_roast_premium_success(mock_model, mock_check_premium):
    mock_check_premium.return_value = True
    
    # Mock Gemini model response
    mock_response = MagicMock()
    mock_response.text = '{"roast": "This deck is absolute garbage.", "salt_score": 85, "verdict": "Salt shaker"}'
    mock_model.generate_content.return_value = mock_response
    
    payload = {
        "benutzername": "premium_user",
        "deck_liste": "1 Sol Ring",
        "format": "commander"
    }
    response = client.post("/api/deck/roast", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "roast" in data
    assert data["salt_score"] == 85
    assert data["verdict"] == "Salt shaker"


@pytest.mark.asyncio
@patch('routers.decks.fetch_card_details_cached')
async def test_deck_stats_success(mock_fetch):
    mock_fetch.return_value = {
        "sol ring": {
            "name": "Sol Ring",
            "cmc": 1.0,
            "colors": [],
            "type": "Artifact"
        },
        "grizzly bears": {
            "name": "Grizzly Bears",
            "cmc": 2.0,
            "colors": ["G"],
            "type": "Creature"
        }
    }
    payload = {
        "benutzername": "test_user",
        "deck_liste": "1 Sol Ring\n2 Grizzly Bears",
        "format": "commander"
    }
    response = client.post("/api/deck/stats", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "cmc" in data
    assert "cmc_creatures" in data
    assert "cmc_noncreatures" in data
    assert "colors" in data
    
    assert data["cmc"]["1"] == 1
    assert data["cmc"]["2"] == 2
    assert data["cmc_creatures"]["2"] == 2
    assert "1" not in data["cmc_creatures"]
    assert data["cmc_noncreatures"]["1"] == 1
    assert "2" not in data["cmc_noncreatures"]
    assert data["colors"]["G"] == 2
    assert data["colors"]["C"] == 1

