"""
tests/test_cross_user_access.py – Beweist die Behebung der Broken-Access-Control-
Schwachstelle aus dem Sicherheits-Audit: fast alle Endpunkte vertrauten einem vom
Client mitgeschickten `benutzername` statt der echten, per JWT verifizierten
Identität. Diese Tests laufen gegen eine echte (in-memory) SQLite-Datenbank und
beweisen, dass ein eingeloggter Nutzer A weder Daten von Nutzer B lesen noch
verändern/löschen kann, selbst wenn er B's Namen im Request-Body/Query/Pfad
mitschickt -- und dass Premium-Checks jetzt an der Token-Identität hängen, nicht
am (fälschbaren) Client-Feld.
"""

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch

from main import app
from auth import create_access_token
from database import Base

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


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


# ============================================================================
# Decks: Nutzer B darf weder die Deckliste noch die Existenz eines Decks von
# Nutzer A lesen, ändern, löschen oder bearbeiten -- selbst wenn er A's
# Benutzernamen im Pfad/Body mitschickt. Die JWT-Identität entscheidet.
# ============================================================================

@pytest.mark.asyncio
async def test_get_decks_rejects_mismatched_username():
    """Bob ist eingeloggt, fragt aber /api/decks/alice ab (Alice's Pfad-Segment).
    Muss 403 liefern, ohne dass überhaupt eine DB-Abfrage versucht wird."""
    with patch('routers.decks.get_db_session') as mock_get_db:
        response = client.get("/api/decks/alice", headers=_auth_headers("bob"))
        assert response.status_code == 403
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
async def test_update_deck_rejects_non_owner_end_to_end(real_db_session_factory):
    session_maker = real_db_session_factory
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO decks (benutzername, name, liste, format) VALUES ('alice', 'Alice Deck', '1 Sol Ring', 'commander')"),
        )
        await session.commit()
        deck_id = (await session.execute(text("SELECT id FROM decks WHERE benutzername='alice'"))).scalar()

    with patch('routers.decks.get_db_session', _real_get_db_session(session_maker)):
        response = client.post(
            "/api/decks/update",
            json={"deck_id": deck_id, "deck_liste": "1 Black Lotus (HACKED BY BOB)"},
            headers=_auth_headers("bob"),
        )
        assert response.status_code == 403

    async with session_maker() as session:
        row = (await session.execute(text("SELECT liste FROM decks WHERE id = :id"), {"id": deck_id})).mappings().first()
        assert row["liste"] == "1 Sol Ring"


@pytest.mark.asyncio
async def test_delete_deck_does_not_delete_other_users_deck(real_db_session_factory):
    session_maker = real_db_session_factory
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO decks (benutzername, name, liste, format) VALUES ('alice', 'Alice Deck', '1 Sol Ring', 'commander')"),
        )
        await session.commit()
        deck_id = (await session.execute(text("SELECT id FROM decks WHERE benutzername='alice'"))).scalar()

    with patch('routers.decks.get_db_session', _real_get_db_session(session_maker)):
        response = client.post(
            "/api/decks/loeschen",
            json={"deck_id": deck_id, "benutzername": "alice"},
            headers=_auth_headers("bob"),
        )
        # Der Endpoint antwortet unverändert mit erfolg=True (kein Leak, ob die
        # ID existiert) -- entscheidend ist, dass NICHTS gelöscht wurde.
        assert response.status_code == 200

    async with session_maker() as session:
        row = (await session.execute(text("SELECT id FROM decks WHERE id = :id"), {"id": deck_id})).mappings().first()
        assert row is not None, "Bob durfte Alice's Deck nicht löschen können"


@pytest.mark.asyncio
async def test_add_card_rejects_non_owner_end_to_end(real_db_session_factory):
    session_maker = real_db_session_factory
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO decks (benutzername, name, liste, format) VALUES ('alice', 'Alice Deck', '1 Sol Ring', 'commander')"),
        )
        await session.commit()
        deck_id = (await session.execute(text("SELECT id FROM decks WHERE benutzername='alice'"))).scalar()

    with patch('routers.decks.get_db_session', _real_get_db_session(session_maker)):
        response = client.post(
            "/api/deck/add-card",
            json={"deck_id": deck_id, "card_name": "Black Lotus", "benutzername": "alice"},
            headers=_auth_headers("bob"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["erfolg"] is False

    async with session_maker() as session:
        row = (await session.execute(text("SELECT liste FROM decks WHERE id = :id"), {"id": deck_id})).mappings().first()
        assert row["liste"] == "1 Sol Ring"


@pytest.mark.asyncio
async def test_deck_analyse_premium_check_uses_token_identity_not_spoofed_body(real_db_session_factory):
    """Bob (free) schickt im Body benutzername='alice' (Premium), um die
    Paywall zu umgehen und Alice's KI-Kontingent zu verbrauchen. Muss trotzdem
    die Paywall-Antwort bekommen, weil der Premium-Check jetzt an Bobs
    Token-Identität hängt, nicht am Body-Feld."""
    session_maker = real_db_session_factory
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES ('alice', 'x', 'premium')"),
        )
        await session.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES ('bob', 'x', 'free')"),
        )
        await session.commit()

    # Body behauptet, der Aufrufer sei die echte, existierende Premium-Nutzerin
    # 'alice' -- mit der alten, verwundbaren Implementierung (check_user_premium
    # auf dem Body-Feld) hätte das die Paywall umgangen und Alice's Kontingent
    # verbraucht. Die Token-Identität ist aber 'bob' (free).
    with patch('database.async_session', session_maker):
        response = client.post(
            "/api/deck/analyse",
            json={"deck_liste": "1 Sol Ring", "benutzername": "alice", "format": "commander"},
            headers=_auth_headers("bob"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("error") == "paywall"


# ============================================================================
# Sammlung: analoge Beweise für die Collection-Endpunkte.
# ============================================================================

@pytest.mark.asyncio
async def test_get_sammlung_rejects_mismatched_username():
    with patch('routers.collection.get_db_session') as mock_get_db:
        response = client.get("/api/sammlung/alice", headers=_auth_headers("bob"))
        assert response.status_code == 403
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("pfad", [
    "/api/sammlung/alice/uebersicht",
    "/api/sammlung/alice/top",
    "/api/sammlung/alice/alben",
    "/api/sammlung/alice/kartennamen?album=Ordner%201",
])
async def test_neue_sammlungsrouten_lehnen_fremden_namen_ab(pfad):
    """Die schlanken Ansichten (Uebersicht, Top-Liste, Ordnernamen) sind neue
    Wege zu denselben Daten. Sie muessen dieselbe Huerde haben wie der alte
    Endpunkt -- sonst waere die Sammlung ueber die Hintertuer lesbar."""
    with patch('routers.collection.get_db_session') as mock_get_db:
        response = client.get(pfad, headers=_auth_headers("bob"))

        assert response.status_code == 403, pfad
        # Nicht erst abfragen und dann verwerfen: bei 403 darf die Datenbank
        # gar nicht erst angefasst werden.
        mock_get_db.assert_not_called()


@pytest.mark.asyncio
async def test_delete_karte_does_not_delete_other_users_card(real_db_session_factory):
    """Vorher hatte /api/sammlung/loeschen ueberhaupt keine Besitzpruefung --
    jede beliebige karten_id konnte von jedem geloescht werden."""
    session_maker = real_db_session_factory
    async with session_maker() as session:
        await session.execute(
            text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
                 "VALUES ('alice', 'Sol Ring', 'Standard', '', '1.50')"),
        )
        await session.commit()
        karten_id = (await session.execute(text("SELECT id FROM sammlung_alben WHERE benutzername='alice'"))).scalar()

    with patch('routers.collection.get_db_session', _real_get_db_session(session_maker)):
        response = client.post(
            "/api/sammlung/loeschen",
            json={"karten_id": karten_id},
            headers=_auth_headers("bob"),
        )
        assert response.status_code == 200

    async with session_maker() as session:
        row = (await session.execute(text("SELECT id FROM sammlung_alben WHERE id = :id"), {"id": karten_id})).mappings().first()
        assert row is not None, "Bob durfte Alice's Sammlungskarte nicht löschen können"


# ============================================================================
# KI-Endpunkte: Premium-Check und Kontingent-Zuordnung müssen an der
# Token-Identität hängen, nicht am (fälschbaren) Body-Feld.
# ============================================================================

@pytest.mark.asyncio
@patch('routers.ai.check_user_premium', new_callable=AsyncMock)
async def test_judge_premium_check_uses_token_identity_not_spoofed_body(mock_check_premium):
    mock_check_premium.return_value = False

    response = client.post(
        "/api/judge",
        json={"frage": "Was ist Trample?", "benutzername": "alice_premium"},
        headers=_auth_headers("bob"),
    )

    assert response.status_code == 200
    assert "PAYWALL" in response.json()["antwort"]
    # Entscheidender Beweis: der Premium-Check wurde mit Bobs echter
    # Identität aufgerufen, nicht mit dem gespooften Body-Feld.
    mock_check_premium.assert_called_once_with("bob")


# ============================================================================
# Payments: die Stripe-Metadaten (die später vom Webhook zur Rollenvergabe
# genutzt werden) müssen an der Token-Identität hängen.
# ============================================================================

@pytest.mark.asyncio
async def test_checkout_session_uses_token_identity_not_spoofed_body(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    response = client.post(
        "/api/checkout/create-session",
        json={"benutzername": "alice", "host_url": "http://localhost:5175"},
        headers=_auth_headers("bob"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["simulated"] is True
    assert "user=bob" in data["url"]
    assert "user=alice" not in data["url"]
