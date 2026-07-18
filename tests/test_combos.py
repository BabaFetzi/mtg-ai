import pytest
from services.combos import detect_local_combos
from fastapi.testclient import TestClient
from main import app
from auth import create_access_token
from unittest.mock import patch, AsyncMock, MagicMock

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

def test_detect_local_combos_empty():
    assert detect_local_combos("") == []
    assert detect_local_combos("   ") == []

def test_detect_local_combos_no_match():
    decklist = "1 Sol Ring\n4 Lightning Bolt\n1 Arcane Signet\n35 Mountain"
    assert detect_local_combos(decklist) == []

def test_detect_local_combos_single_match():
    # Godo + Helm combo
    decklist = "1 Godo, Bandit Warlord\n1 Helm of the Host\n38 Mountain"
    combos = detect_local_combos(decklist)
    assert len(combos) == 1
    assert combos[0]["name"] == "Godo, Bandit Warlord + Helm of the Host"
    assert "Helm des Wirts" in combos[0]["grund"]

def test_detect_local_combos_multiple_matches():
    # Oracle + Consult AND Sanguine Bond + Exquisite Blood
    decklist = (
        "1 Thassa's Oracle\n"
        "1 Demonic Consultation\n"
        "1 Sanguine Bond\n"
        "1 Exquisite Blood\n"
        "36 Swamp"
    )
    combos = detect_local_combos(decklist)
    assert len(combos) == 2
    combo_names = {c["name"] for c in combos}
    assert "Thassa's Oracle + Demonic Consultation" in combo_names
    assert "Sanguine Bond + Exquisite Blood" in combo_names

@pytest.mark.asyncio
@patch('routers.ai.check_user_premium')
@patch('routers.ai.get_db_session')
@patch('routers.ai.scryfall_cache')
async def test_scan_combos_cache_hit(mock_cache, mock_get_db, mock_check_premium):
    mock_check_premium.return_value = True
    
    # Mock cache returning a hits payload directly
    cached_payload = {
        "combos": [
            {"name": "Godo, Bandit Warlord + Helm of the Host", "grund": "Instant Win"}
        ]
    }
    mock_cache.get.return_value = cached_payload
    
    payload = {
        "karten_liste": "1 Godo, Bandit Warlord\n1 Helm of the Host",
        "benutzername": "premium_user",
        "format": "commander"
    }
    
    response = client.post("/api/scan_combos", json=payload, headers=_auth_headers("premium_user"))
    assert response.status_code == 200
    assert response.json() == cached_payload
    
    # Database session shouldn't be touched if cache hit
    assert mock_get_db.call_count == 0
