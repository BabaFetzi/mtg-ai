import pytest
from fastapi.testclient import TestClient
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch
from main import app

client = TestClient(app)

@pytest.mark.asyncio
@patch('main.fetch_card_details_cached')
async def test_sammlung_filter(mock_fetch):
    # Mock Scryfall cache response
    mock_fetch.return_value = {
        "sol ring": {
            "name": "Sol Ring",
            "type": "Artifact",
            "colors": [],
            "color_identity": [],
            "cmc": 1.0,
            "rarity": "uncommon",
            "set": "c21",
            "image": "https://example.com/solring.jpg",
            "price": "1.50",
            "set_name": "Commander 2021"
        }
    }

    # Patch the sqlite database connection inside endpoint
    # Since we can mock the aiosqlite return values
    with patch('main.get_db_session') as mock_get_db:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        row = {
            "id": 1,
            "benutzername": "testuser",
            "karten_name": "Sol Ring",
            "album_name": "Standard",
            "bild_url": "https://example.com/solring.jpg",
            "preis": "1.50"
        }
        
        mock_result.mappings.return_value.all.return_value = [row]
        mock_session.execute.return_value = mock_result
        mock_get_db.return_value.__aenter__.return_value = mock_session

        # Test request
        response = client.get("/api/sammlung/testuser/filter?suche=Sol")
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert len(data["karten"]) == 1
        assert data["karten"][0]["name"] == "Sol Ring"

@pytest.mark.asyncio
@patch('main.fetch_card_details_cached')
async def test_sammlung_editions(mock_fetch):
    mock_fetch.return_value = {
        "sol ring": {
            "set": "c21",
            "set_name": "Commander 2021"
        }
    }

    with patch('main.get_db_session') as mock_get_db:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        rows = [{"karten_name": "Sol Ring"}]
        mock_result.mappings.return_value.all.return_value = rows
        mock_session.execute.return_value = mock_result
        mock_get_db.return_value.__aenter__.return_value = mock_session

        response = client.get("/api/sammlung/testuser/editions")
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert len(data["editions"]) == 1
        assert data["editions"][0]["set_code"] == "c21"

def test_csv_import_template():
    # Helper to check file uploads mock
    csv_data = "Kartenname,Anzahl,Edition,Album\nSol Ring,1,C21,Standard\n"
    
    with patch('main.fetch_card_details_cached') as mock_fetch, \
         patch('main.get_db_session') as mock_get_db:
        
        mock_fetch.return_value = {
            "sol ring": {
                "name": "Sol Ring",
                "image": "https://example.com/solring.jpg",
                "price": "1.50"
            }
        }
        
        mock_session = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        file_payload = {"file": ("test.csv", io.BytesIO(csv_data.encode("utf-8-sig")), "text/csv")}
        form_payload = {"benutzername": "testuser", "album_name": "Standard"}
        
        response = client.post("/api/sammlung/import-csv", files=file_payload, data=form_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert data["imported"] == 1
        assert data["failed"] == 0
