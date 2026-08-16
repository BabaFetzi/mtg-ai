import pytest
from fastapi.testclient import TestClient
import io
import json
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from auth import create_access_token

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

@pytest.mark.asyncio
@patch('routers.collection.fetch_card_details_cached')
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
    with patch('routers.collection.get_db_session') as mock_get_db:
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
        response = client.get("/api/sammlung/testuser/filter?suche=Sol", headers=_auth_headers("testuser"))
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert len(data["karten"]) == 1
        assert data["karten"][0]["name"] == "Sol Ring"

@pytest.mark.asyncio
@patch('routers.collection.fetch_card_details_cached')
async def test_sammlung_editions(mock_fetch):
    """Zeilen ohne gespeicherte Edition (Altbestand) werden weiterhin ueber
    den Namen aufgeloest -- sonst verschwaenden sie aus der Auswahl, bis die
    Wartungsaufgabe die Spalte nachgefuellt hat."""
    mock_fetch.return_value = {
        "sol ring": {"set": "c21", "set_name": "Commander 2021"}
    }

    with patch('routers.collection.get_db_session') as mock_get_db:
        mock_session = AsyncMock()

        def _antwort(sql, params=None):
            ergebnis = MagicMock()
            # Erste Abfrage: Editionen aus der Spalte. Zweite: Zeilen ohne.
            if "GROUP BY edition" in sql.text:
                ergebnis.mappings.return_value.all.return_value = []
            else:
                ergebnis.mappings.return_value.all.return_value = [
                    {"karten_name": "Sol Ring"}]
            return ergebnis

        mock_session.execute.side_effect = _antwort
        mock_get_db.return_value.__aenter__.return_value = mock_session

        response = client.get("/api/sammlung/testuser/editions", headers=_auth_headers("testuser"))
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert len(data["editions"]) == 1
        assert data["editions"][0]["set_code"] == "c21"

@pytest.mark.asyncio
async def test_csv_import_template():
    # Helper to check file uploads mock
    csv_data = "Kartenname,Anzahl,Edition,Album\nSol Ring,1,C21,Standard\n"
    
    with patch('routers.collection.fetch_card_details_cached') as mock_fetch, \
         patch('routers.collection.get_db_session') as mock_get_db:
        
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
        form_payload = {"album_name": "Standard"}

        response = client.post("/api/sammlung/import-csv", files=file_payload, data=form_payload, headers=_auth_headers("testuser"))
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert "job_id" in data
        
        from routers.collection import run_csv_import_task
        await run_csv_import_task(data["job_id"], csv_data, "testuser", "Standard")
        
        assert mock_session.execute.call_count >= 2


@pytest.mark.asyncio
@patch('routers.collection.check_user_premium')
@patch('routers.collection.fetch_card_details_cached')
async def test_refresh_sammlung_prices(mock_fetch, mock_check_premium):
    mock_check_premium.return_value = True
    mock_fetch.return_value = {
        "sol ring": {
            "name": "Sol Ring",
            "price": "2.00"
        }
    }
    with patch('routers.collection.get_db_session') as mock_get_db, \
         patch('services.cache.scryfall_cache.delete') as mock_cache_delete:
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        rows = [{"karten_name": "Sol Ring"}]
        mock_result.mappings.return_value.all.return_value = rows
        mock_session.execute.return_value = mock_result
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.post("/api/sammlung/testuser/refresh-prices", headers=_auth_headers("testuser"))
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is True
        assert mock_cache_delete.call_count >= 1


@pytest.mark.asyncio
@patch('routers.collection.check_user_premium')
async def test_refresh_sammlung_prices_free_denied(mock_check_premium):
    mock_check_premium.return_value = False
    response = client.post("/api/sammlung/testuser/refresh-prices", headers=_auth_headers("testuser"))
    assert response.status_code == 403
    assert response.json()["erfolg"] is False
    assert "Paywall" in response.json()["error"]

