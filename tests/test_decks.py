from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from auth import create_access_token
from database import Base

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

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
    
    response = client.post("/api/decks/erstellen", json=payload, headers=_auth_headers("premium_user"))
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
    
    response = client.post("/api/decks/erstellen", json=payload, headers=_auth_headers("free_user"))
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
    
    response = client.post("/api/decks/erstellen", json=payload, headers=_auth_headers("free_user"))
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
    response = client.post("/api/deck/roast", json=payload, headers=_auth_headers("free_user"))
    assert response.status_code == 200
    assert response.json()["error"] == "paywall"

@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
@patch('services.ai_service.model_lite')
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
    response = client.post("/api/deck/roast", json=payload, headers=_auth_headers("premium_user"))
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
    # /deck/stats verlangt jetzt einen Login (der Endpunkt verbraucht das
    # gemeinsame Scryfall-Budget und war zuvor für jeden offen).
    assert client.post("/api/deck/stats", json=payload).status_code == 401

    response = client.post("/api/deck/stats", json=payload, headers=_auth_headers("test_user"))
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


# ============================================================================
# Regression test: routers/decks.py must use the real `decks` table columns
# (`name`, `liste`) rather than the non-existent `deck_name`/`deck_liste`.
# Runs against a real (in-memory) SQLite schema created from database.py's
# models, so a column-name mismatch fails loudly instead of being hidden by
# a mocked session.
# ============================================================================
@pytest_asyncio.fixture
async def real_db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    yield session_maker
    await engine.dispose()


def _real_get_db_session(session_maker):
    @asynccontextmanager
    async def _get_db_session():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get_db_session


@pytest.mark.asyncio
@patch('routers.decks.fetch_card_details_cached')
@patch('routers.decks.check_user_premium')
async def test_deck_save_and_load_roundtrip_against_real_schema(mock_check_premium, mock_fetch, real_db_session_factory):
    """Proves the deck-save bug is fixed: create a deck via the real API,
    then load it back via the real API, against the actual `decks` table
    schema (columns `name`/`liste`) -- not a mock."""
    mock_check_premium.return_value = True
    mock_fetch.return_value = {
        "sol ring": {"name": "Sol Ring", "cmc": 1.0, "colors": [], "type": "Artifact", "price": "1.20"},
        "command tower": {"name": "Command Tower", "cmc": 0.0, "colors": [], "type": "Land", "price": "0.25"},
    }

    with patch('routers.decks.get_db_session', _real_get_db_session(real_db_session_factory)):
        create_payload = {
            "benutzername": "roundtrip_user",
            "deck_name": "Meine Testliste",
            "deck_liste": "1 Sol Ring\n1 Command Tower",
            "format": "commander",
        }
        create_resp = client.post("/api/decks/erstellen", json=create_payload, headers=_auth_headers("roundtrip_user"))
        assert create_resp.status_code == 200
        assert create_resp.json()["erfolg"] is True

        load_resp = client.get("/api/decks/roundtrip_user", headers=_auth_headers("roundtrip_user"))
        assert load_resp.status_code == 200
        decks = load_resp.json()
        assert len(decks) == 1
        assert decks[0]["name"] == "Meine Testliste"
        assert decks[0]["liste"] == "1 Sol Ring\n1 Command Tower"
        assert decks[0]["format"] == "commander"
        assert decks[0]["card_count"] == 2
        assert decks[0]["price"] == "1.45"
        assert decks[0]["updated_at"] is not None


@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_remove_card_decrements_even_with_case_and_x_format(mock_check_premium, real_db_session_factory):
    """Regression (T-4.1): Verringern schlug fehl, weil remove-card exakt
    verglich, während add-card über clean_card_name normalisiert. Ein '2x'-Eintrag
    muss auch bei abweichender Groß-/Kleinschreibung auf '1x' dekrementiert werden."""
    mock_check_premium.return_value = True
    with patch('routers.decks.get_db_session', _real_get_db_session(real_db_session_factory)):
        create_resp = client.post(
            "/api/decks/erstellen",
            json={
                "benutzername": "remover",
                "deck_name": "Remove Test",
                "deck_liste": "2x Sol Ring",
                "format": "commander",
            },
            headers=_auth_headers("remover"),
        )
        assert create_resp.status_code == 200
        deck_id = client.get("/api/decks/remover", headers=_auth_headers("remover")).json()[0]["id"]

        # Andere Schreibweise als gespeichert -> muss trotzdem greifen.
        resp = client.post(
            "/api/deck/remove-card",
            json={"deck_id": deck_id, "card_name": "sol ring"},
            headers=_auth_headers("remover"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["erfolg"] is True, body
        assert body["deck_liste"].strip() == "1x Sol Ring"



@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_analysis_fallback_invents_no_scores(mock_premium):
    """Ohne KI-Antwort darf KEINE Bewertung erfunden werden. Vorher standen hier
    überall score 5 und power_level 5 -- im Frontend sah das aus wie ein echtes
    Ergebnis."""
    mock_premium.return_value = True
    with patch('services.ai_service.model', None):
        resp = client.post(
            "/api/deck/analyse",
            json={"deck_liste": "1 Sol Ring", "format": "commander"},
            headers=_auth_headers("premium_user"),
        )
    body = resp.json()
    assert body["nicht_verfuegbar"] is True
    assert body["power_level"] is None
    assert body["schwaechen"] == {}
    assert "nicht verfügbar" in body["strategie"]


@pytest.mark.asyncio
@patch('routers.decks.check_user_premium')
async def test_roast_fallback_invents_no_salt_score(mock_premium):
    mock_premium.return_value = True
    with patch('services.ai_service.model_lite', None):
        resp = client.post(
            "/api/deck/roast",
            json={"deck_liste": "1 Sol Ring", "format": "commander"},
            headers=_auth_headers("premium_user"),
        )
    body = resp.json()
    assert body["nicht_verfuegbar"] is True
    assert body["salt_score"] is None
    assert body["verdict"] is None


@pytest.mark.asyncio
async def test_dashboard_counts_real_collection_cards(real_db_session_factory):
    """Regression: Das Dashboard zeigte dauerhaft 0 Karten, weil es SUM(anzahl)
    las -- eine Spalte, die von den Roh-SQL-Inserts nie gesetzt wird."""
    from sqlalchemy import text as sql_text
    async with real_db_session_factory() as s:
        await s.execute(sql_text(
            "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
            "VALUES ('u','Sol Ring','A','',' 1.0'), ('u','Lightning Bolt','A','','1.0'), "
            "       ('u','__PLACEHOLDER__','Leer','','0.00')"
        ))
        await s.commit()

    with patch('routers.decks.get_db_session', _real_get_db_session(real_db_session_factory)):
        resp = client.get("/api/dashboard/stats")

    body = resp.json()
    assert body["total_collection_cards"] == 2, body
    assert body["total_albums"] == 2
