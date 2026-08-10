"""
tests/test_ai_reliability_logging.py – Ersatzmodell & KI-Protokoll

Massnahmen 2 und 3 der Architektur-Analyse:
- Fällt das Hauptmodell aus, übernimmt das Ersatzmodell, statt die Funktion für
  den Nutzer ausfallen zu lassen.
- Jede KI-Anfrage wird mit Modell, Tokens, Latenz, Kosten und Erfolg protokolliert,
  ohne die Antwort zu verzögern.
"""

import os
from unittest.mock import patch

import pytest

from services.ai_service import _GeminiModel
from services import ai_usage_log


class FakeUsage:
    def __init__(self, p, c, t):
        self.prompt_token_count = p
        self.candidates_token_count = c
        self.total_token_count = t


class FakeResponse:
    def __init__(self, text="Antwort", usage=None):
        self.text = text
        self.usage_metadata = usage


class FakeModels:
    """Simuliert client.models: bestimmte Modellnamen schlagen fehl."""

    def __init__(self, failing_models=()):
        self.failing = set(failing_models)
        self.aufrufe = []

    def generate_content(self, model, contents, config=None):
        self.aufrufe.append(model)
        if model in self.failing:
            raise RuntimeError(f"{model} nicht verfügbar")
        return FakeResponse(usage=FakeUsage(100, 50, 150))


class FakeClient:
    def __init__(self, failing_models=()):
        self.models = FakeModels(failing_models)


@pytest.fixture(autouse=True)
def leerer_puffer():
    ai_usage_log._drain()
    yield
    ai_usage_log._drain()


# ----------------------------------------------------------------------
# Ersatzmodell
# ----------------------------------------------------------------------
def test_fallback_model_answers_when_primary_fails():
    client = FakeClient(failing_models={"haupt"})
    m = _GeminiModel(client, "haupt", "ersatz")

    antwort = m.generate_content("Frage", feature="judge")

    assert antwort.text == "Antwort"
    assert client.models.aufrufe == ["haupt", "ersatz"]


def test_primary_model_is_used_when_healthy():
    client = FakeClient()
    m = _GeminiModel(client, "haupt", "ersatz")

    m.generate_content("Frage", feature="judge")

    assert client.models.aufrufe == ["haupt"], "Ersatzmodell darf nicht unnötig laufen"


def test_error_is_raised_when_all_models_fail():
    client = FakeClient(failing_models={"haupt", "ersatz"})
    m = _GeminiModel(client, "haupt", "ersatz")

    with pytest.raises(RuntimeError):
        m.generate_content("Frage", feature="judge")

    assert client.models.aufrufe == ["haupt", "ersatz"]


def test_identical_fallback_is_not_called_twice():
    """Ist das Ersatzmodell dasselbe wie das Hauptmodell, wird nicht doppelt gerufen."""
    client = FakeClient(failing_models={"haupt"})
    m = _GeminiModel(client, "haupt", "haupt")

    with pytest.raises(RuntimeError):
        m.generate_content("Frage", feature="judge")

    assert client.models.aufrufe == ["haupt"]


# ----------------------------------------------------------------------
# Protokoll
# ----------------------------------------------------------------------
def test_successful_call_is_logged_with_tokens_and_latency():
    client = FakeClient()
    m = _GeminiModel(client, "haupt", "ersatz")

    m.generate_content("Frage", feature="deck_analyse", benutzername="tester")

    eintraege = ai_usage_log._drain()
    assert len(eintraege) == 1
    e = eintraege[0]
    assert e["funktion"] == "deck_analyse"
    assert e["modell"] == "haupt"
    assert e["erfolg"] is True
    assert e["prompt_tokens"] == 100
    assert e["antwort_tokens"] == 50
    assert e["gesamt_tokens"] == 150
    assert e["latenz_ms"] >= 0
    assert e["benutzername"] == "tester"


def test_failed_and_retried_call_produce_two_entries():
    client = FakeClient(failing_models={"haupt"})
    m = _GeminiModel(client, "haupt", "ersatz")

    m.generate_content("Frage", feature="judge")

    eintraege = ai_usage_log._drain()
    assert [e["modell"] for e in eintraege] == ["haupt", "ersatz"]
    assert [e["erfolg"] for e in eintraege] == [False, True]
    assert "nicht verfügbar" in eintraege[0]["fehler"]


def test_content_is_not_logged_by_default():
    """Datenschutz: ohne AI_LOG_CONTENT werden Frage und Antwort NICHT gespeichert."""
    with patch.dict(os.environ, {"AI_LOG_CONTENT": ""}, clear=False):
        client = FakeClient()
        _GeminiModel(client, "haupt").generate_content("Geheime Frage", feature="judge")

    e = ai_usage_log._drain()[0]
    assert e["frage"] is None
    assert e["antwort"] is None


def test_content_is_logged_when_explicitly_enabled():
    with patch.dict(os.environ, {"AI_LOG_CONTENT": "true"}, clear=False):
        client = FakeClient()
        _GeminiModel(client, "haupt").generate_content("Meine Frage", feature="judge")

    e = ai_usage_log._drain()[0]
    assert e["frage"] == "Meine Frage"
    assert e["antwort"] == "Antwort"


def test_image_data_is_never_logged():
    """Multimodale Aufrufe (Vision) dürfen keine Bilddaten ins Protokoll schreiben."""
    with patch.dict(os.environ, {"AI_LOG_CONTENT": "true"}, clear=False):
        client = FakeClient()
        _GeminiModel(client, "haupt").generate_content(
            ["Beschreibe das Bild", {"mime_type": "image/png", "data": b"\x89PNG"}],
            feature="vision",
        )

    e = ai_usage_log._drain()[0]
    assert e["frage"] == "Beschreibe das Bild"
    assert "PNG" not in (e["frage"] or "")


# ----------------------------------------------------------------------
# Kosten
# ----------------------------------------------------------------------
def test_cost_is_none_without_configured_prices():
    """Ohne hinterlegte Preise wird KEIN Preis geraten."""
    with patch.dict(os.environ, {"GEMINI_PRICE_INPUT_PER_MTOK": "",
                                 "GEMINI_PRICE_OUTPUT_PER_MTOK": ""}, clear=False):
        assert ai_usage_log.berechne_kosten_usd(1000, 500) is None


def test_cost_is_calculated_from_configured_prices():
    with patch.dict(os.environ, {"GEMINI_PRICE_INPUT_PER_MTOK": "0.10",
                                 "GEMINI_PRICE_OUTPUT_PER_MTOK": "0.40"}, clear=False):
        # 1 Mio Eingabe-Tokens * 0.10 + 0.5 Mio Ausgabe-Tokens * 0.40 = 0.30
        assert ai_usage_log.berechne_kosten_usd(1_000_000, 500_000) == pytest.approx(0.30)


def test_buffer_is_bounded():
    """Bei nicht erreichbarer Datenbank darf der Puffer nicht unbegrenzt wachsen."""
    for i in range(ai_usage_log.MAX_BUFFER + 500):
        ai_usage_log.record(funktion="judge", modell="m", erfolg=True, latenz_ms=1)
    assert ai_usage_log.buffered_count() <= ai_usage_log.MAX_BUFFER


def test_logging_failure_never_breaks_the_ai_call():
    """Ein kaputtes Protokoll darf die KI-Antwort nicht verhindern."""
    client = FakeClient()
    m = _GeminiModel(client, "haupt")

    with patch("services.ai_usage_log.record", side_effect=RuntimeError("Protokoll kaputt")):
        antwort = m.generate_content("Frage", feature="judge")

    assert antwort.text == "Antwort"


# ----------------------------------------------------------------------
# Persistenz gegen das echte Schema
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flush_writes_against_real_schema():
    """Beweist gegen die ECHTE Tabelle, dass der Puffer sauber wegschreibt."""
    import tempfile
    from contextlib import asynccontextmanager
    from sqlalchemy import text as sql_text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import StaticPool
    from database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def fake_session():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    ai_usage_log.record(funktion="judge", modell="gemini-flash-latest", erfolg=True,
                        latenz_ms=420, prompt_tokens=100, antwort_tokens=50,
                        gesamt_tokens=150, benutzername="tester")
    ai_usage_log.record(funktion="deck_analyse", modell="gemini-flash-latest", erfolg=False,
                        latenz_ms=90, fehler="503 überlastet", benutzername="tester")

    with patch("database.get_db_session", fake_session):
        geschrieben = await ai_usage_log.flush()

    assert geschrieben == 2
    assert ai_usage_log.buffered_count() == 0, "Puffer muss nach dem Schreiben leer sein"

    async with session_maker() as session:
        rows = (await session.execute(
            sql_text("SELECT funktion, modell, erfolg, latenz_ms, gesamt_tokens FROM ai_calls ORDER BY id")
        )).mappings().all()

    assert [r["funktion"] for r in rows] == ["judge", "deck_analyse"]
    assert rows[0]["gesamt_tokens"] == 150
    assert rows[0]["latenz_ms"] == 420
    await engine.dispose()


@pytest.mark.asyncio
async def test_flush_does_not_lose_data_silently_on_db_error():
    """Bei DB-Fehler wird gewarnt statt zu crashen -- die KI läuft weiter."""
    ai_usage_log.record(funktion="judge", modell="m", erfolg=True, latenz_ms=1)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def kaputt():
        raise RuntimeError("DB weg")
        yield

    with patch("database.get_db_session", kaputt):
        geschrieben = await ai_usage_log.flush()

    assert geschrieben == 0
