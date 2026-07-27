"""
tests/test_hardening.py – Absicherung & Dauerbetrieb

Deckt die Funde des Gesamt-Audits ab:

1. Bisher offene, teure Endpunkte verlangen jetzt einen Login (sie verbrauchen
   das gemeinsame Scryfall-Budget und waren für jeden im Netz aufrufbar).
2. /user/role gibt den Abo-Status nicht mehr für fremde Konten preis
   (Konto-Enumeration).
3. Der Login-Ratenbegrenzer wächst nicht mehr unbegrenzt im Speicher.
4. Die periodische Wartung löscht alte Hintergrund-Jobs (Tabellen wuchsen
   vorher endlos).
5. Validierte Combos tragen exakte Kartennamen (korrekte Kartenbilder).
"""

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

import auth as auth_module
from auth import create_access_token, login_attempts, record_login_attempt
from database import Base
from main import app

client = TestClient(app)


def _auth_headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


# ----------------------------------------------------------------------
# 1. Teure Endpunkte sind nicht mehr offen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("pfad,payload", [
    ("/api/deck/visualize", {"deck_liste": "1 Sol Ring"}),
    ("/api/deck/stats", {"deck_liste": "1 Sol Ring"}),
    ("/api/deck/wert", {"deck_liste": "1 Sol Ring"}),
    ("/api/deck/validate", {"deck_liste": "1 Sol Ring", "format": "commander"}),
])
def test_expensive_deck_endpoints_require_login(pfad, payload):
    """Ohne Login kein Zugriff -- sonst kann jeder im Netz über grosse
    Decklisten unser gemeinsames Scryfall-Kontingent verbrauchen."""
    assert client.post(pfad, json=payload).status_code == 401


# ----------------------------------------------------------------------
# 2. Kein Abo-Status fremder Konten
# ----------------------------------------------------------------------
def test_user_role_requires_login():
    assert client.get("/api/user/role/alice").status_code == 401


def test_user_role_blocks_foreign_lookup():
    """Verhindert Konto-Enumeration und die Offenlegung, wer zahlender Kunde ist."""
    resp = client.get("/api/user/role/alice", headers=_auth_headers("bob"))
    assert resp.status_code == 403


@patch("routers.auth.get_db_session")
def test_user_role_allows_self(mock_db):
    mock_session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {"rolle": "premium"}
    mock_session.execute = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    mock_db.return_value = ctx

    resp = client.get("/api/user/role/alice", headers=_auth_headers("alice"))
    assert resp.status_code == 200
    assert resp.json()["rolle"] == "premium"


# ----------------------------------------------------------------------
# 3. Login-Ratenbegrenzer: begrenzter Speicher
# ----------------------------------------------------------------------
def test_login_attempt_registry_is_pruned():
    """Wer Logins für zehntausende Benutzernamen durchprobiert, darf den
    Serverspeicher nicht volllaufen lassen."""
    login_attempts.clear()
    auth_module._attempt_seen.clear()

    alt = time.time() - (auth_module.LOGIN_ATTEMPT_TTL_SECONDS + 60)
    for i in range(50):
        key = ("1.2.3.4", f"opfer{i}")
        login_attempts[key] = (1, 0.0)          # nicht gesperrt
        auth_module._attempt_seen[key] = alt     # und veraltet

    auth_module._prune_login_attempts(time.time())
    assert login_attempts == {}
    assert auth_module._attempt_seen == {}


def test_pruning_keeps_actively_blocked_entries():
    """Aktive Sperren dürfen NICHT wegoptimiert werden (sonst liesse sich die
    Sperre durch Warten auf die Bereinigung umgehen)."""
    login_attempts.clear()
    auth_module._attempt_seen.clear()

    key = ("9.9.9.9", "angreifer")
    now = time.time()
    login_attempts[key] = (5, now + 900)                      # gesperrt
    auth_module._attempt_seen[key] = now - 999999             # aber alt

    auth_module._prune_login_attempts(now)
    assert key in login_attempts

    login_attempts.clear()
    auth_module._attempt_seen.clear()


def test_successful_login_clears_tracking():
    login_attempts.clear()
    auth_module._attempt_seen.clear()

    record_login_attempt("5.5.5.5", "user", success=False)
    assert ("5.5.5.5", "user") in auth_module._attempt_seen

    record_login_attempt("5.5.5.5", "user", success=True)
    assert ("5.5.5.5", "user") not in login_attempts
    assert ("5.5.5.5", "user") not in auth_module._attempt_seen


# ----------------------------------------------------------------------
# 4. Wartung: alte Jobs werden gelöscht
# ----------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_maintenance_deletes_old_jobs_and_keeps_recent(db_factory):
    """Job-Tabellen wuchsen mit jeder Analyse/jedem Import unbegrenzt."""
    import main as main_module

    @asynccontextmanager
    async def _session():
        async with db_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async with _session() as s:
        await s.execute(text(
            "INSERT INTO synergy_jobs (job_id, status, erstellt_am) VALUES "
            "('alt', 'completed', datetime('now','-3 days')),"
            "('neu', 'completed', datetime('now')),"
            "('legacy', 'completed', NULL)"
        ))
        await s.execute(text(
            "INSERT INTO import_jobs (job_id, status, erstellt_am) VALUES "
            "('alt2', 'completed', datetime('now','-3 days')),"
            "('neu2', 'completed', datetime('now'))"
        ))

    with patch("database.get_db_session", _session), \
         patch.object(main_module, "JOB_RETENTION_HOURS", 24):
        await main_module._run_maintenance()

    async with _session() as s:
        syn = [r[0] for r in (await s.execute(text("SELECT job_id FROM synergy_jobs"))).all()]
        imp = [r[0] for r in (await s.execute(text("SELECT job_id FROM import_jobs"))).all()]

    assert syn == ["neu"], f"unerwartet: {syn}"   # alt + legacy (NULL) entfernt
    assert imp == ["neu2"], f"unerwartet: {imp}"


# ----------------------------------------------------------------------
# 5. Combos tragen exakte Kartennamen
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_validated_combos_carry_exact_card_names():
    """Ohne 'cards' rät das Frontend die Namen aus der Überschrift und zerlegt
    Namen mit Komma falsch ('Ashaya, Soul of the Wild' -> zwei Karten)."""
    from services import combo_validation

    async def fake_fetch(names):
        return {
            "ashaya, soul of the wild": {"name": "Ashaya, Soul of the Wild", "legalities": {"commander": "legal"}},
            "bloom tender": {"name": "Bloom Tender", "legalities": {"commander": "legal"}},
        }

    with patch.object(combo_validation, "fetch_card_details_cached", fake_fetch):
        valide, verworfen = await combo_validation.validate_combos(
            [{"name": "Ashaya, Soul of the Wild + Bloom Tender", "grund": "…"}],
            "commander",
        )

    assert len(valide) == 1 and not verworfen
    assert valide[0]["cards"] == ["Ashaya, Soul of the Wild", "Bloom Tender"]
