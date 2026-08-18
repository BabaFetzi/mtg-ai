import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import json
from main import app
from auth import create_access_token
import main
import routers.decks
import services.ai_service

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

@pytest.fixture
def mock_gemini_response():
    response_data = {
        "strategie": "Aggro-Tribal mit Goblin-Synergie",
        "commander": "Krenko, Mob Boss",
        "staerken": ["Explosive Token-Generierung", "Niedrige Manakurve"],
        "schwaechen": {
            "card_draw": {"score": 3, "text": "Nur wenig Card Draw vorhanden."},
            "removal": {"score": 5, "text": "Geringe Anzahl an Interaktionen."},
            "ramp": {"score": 4, "text": "Keine echte Manabeschleunigung."},
            "protection": {"score": 2, "text": "Kaum Schutz für Krenko."},
            "winconditions": {"score": 8, "text": "Krenko selbst gewinnt Spiele."}
        },
        "synergien": [
            {"karten": ["Krenko, Mob Boss", "Goblin Chieftain"], "erklaerung": "Goblin Chieftain gibt Eile und stärkt Goblins."}
        ],
        "combos": [
            {"karten": ["Kiki-Jiki", "Zealous Conscripts"], "typ": "Infinite", "erklaerung": "Unendlich viele Token mit Eile."}
        ],
        "verbesserungen": [
            {"rein": "Skullclamp", "raus": "Raging Goblin", "grund": "Sehr starker Card Draw für Token."}
        ],
        "format_kontext": "Commander Format-Kontext.",
        "power_level": 7
    }
    return response_data

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_deck_analyse_paywall(mock_premium):
    mock_premium.return_value = False
    
    response = client.post("/api/deck/analyse", json={
        "deck_liste": "1 Krenko, Mob Boss\n1 Goblin Chieftain",
        "benutzername": "testuser",
        "format": "commander"
    }, headers=_auth_headers("testuser"))

    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert data["error"] == "paywall"

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_deck_analyse_success(mock_premium, mock_gemini_response):
    mock_premium.return_value = True
    
    # Mock Gemini model
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_gemini_response)
    mock_model.generate_content.return_value = mock_response
    
    # Temporarily set main.model to mock_model
    original_model = services.ai_service.model
    services.ai_service.model = mock_model
    
    try:
        with patch('routers.decks.scryfall_cache.get', return_value=None):
            response = client.post("/api/deck/analyse", json={
                "deck_liste": "1 Krenko, Mob Boss\n1 Goblin Chieftain",
                "benutzername": "testuser",
                "format": "commander"
            }, headers=_auth_headers("testuser"))

            assert response.status_code == 200
            data = response.json()
            assert data["strategie"] == "Aggro-Tribal mit Goblin-Synergie"
        assert data["power_level"] == 7
        assert data["commander"] == "Krenko, Mob Boss"
        assert len(data["staerken"]) == 2
        assert data["schwaechen"]["card_draw"]["score"] == 3
        
        # Verify arguments passed to generate_content
        mock_model.generate_content.assert_called_once()
        prompt_arg = mock_model.generate_content.call_args[0][0]
        assert "commander" in prompt_arg
        assert "Krenko, Mob Boss" in prompt_arg
    finally:
        services.ai_service.model = original_model

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_deck_analyse_fallback_on_exception(mock_premium):
    mock_premium.return_value = True
    
    # Mock Gemini model to throw an exception
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("API Timeout")
    
    original_model = services.ai_service.model
    services.ai_service.model = mock_model
    
    try:
        with patch('routers.decks.scryfall_cache.get', return_value=None):
            response = client.post("/api/deck/analyse", json={
                "deck_liste": "1 Krenko, Mob Boss",
                "benutzername": "testuser",
                "format": "commander"
            }, headers=_auth_headers("testuser"))

            assert response.status_code == 200
            data = response.json()
            assert "error" not in data
            # Kein erfundenes Ersatz-Ergebnis: ohne KI-Antwort gibt es KEINE
            # Bewertung, sondern eine als solche gekennzeichnete Fehlanzeige.
            assert data["nicht_verfuegbar"] is True
            assert "nicht verfügbar" in data["strategie"]
        assert data["power_level"] is None
    finally:
        services.ai_service.model = original_model
