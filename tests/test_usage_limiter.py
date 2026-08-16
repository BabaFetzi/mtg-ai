"""Das monatliche KI-Limit -- der Zähler, an dem die Kosten hängen.

Früher lag dieser Zähler in Redis, mit einem ausdrücklichen "fail-open": ohne
REDIS_URL wurde das Limit GAR NICHT durchgesetzt. Ein Test hielt genau das fest
("darf NIE greifen"). Diese Entscheidung ist aufgehoben, und zwar bewusst:

Jeder Gemini-Aufruf kostet echtes Geld. Ein vergessenes REDIS_URL oder ein
Redis-Ausfall hätte unbegrenzte Kosten verursacht, ohne dass irgendetwas
auffällt -- und zwar für Gratis-Konten genauso wie für zahlende. Gezählt wird
jetzt in der Datenbank: die ist ohnehin da, gilt über alle Worker hinweg und
übersteht einen Neustart.

Was bleibt: klemmt die Datenbank tatsächlich, wird der Aufruf zugelassen statt
zahlende Nutzer auszusperren. Das ist jetzt der seltene Ausnahmefall und nicht
mehr der Normalzustand jeder Installation ohne Redis.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
import services.usage_limiter as ul


@pytest_asyncio.fixture
async def db():
    """Echte SQLite-Datenbank im Speicher -- kein Mock. Der Zähler steht und
    fällt mit dem UPSERT, und den muss die Datenbank wirklich ausführen."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _sitzung():
        async with macher() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    with patch("database.get_db_session", _sitzung):
        yield macher

    await engine.dispose()


# ----------------------------------------------------------------------
# Text-Limit
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_zaehlt_bis_zum_limit_und_sperrt_dann(db):
    ergebnisse = [await ul.check_and_increment_ai_usage("nutzer", limit=3)
                  for _ in range(5)]

    assert ergebnisse == [True, True, True, False, False]


@pytest.mark.asyncio
async def test_jeder_nutzer_hat_ein_eigenes_budget(db):
    for _ in range(3):
        assert await ul.check_and_increment_ai_usage("anna", limit=3) is True
    assert await ul.check_and_increment_ai_usage("anna", limit=3) is False

    assert await ul.check_and_increment_ai_usage("bert", limit=3) is True


@pytest.mark.asyncio
async def test_ohne_nutzernamen_wird_nicht_gesperrt(db):
    # Ein anonymer Aufruf darf nicht versehentlich irgendjemanden aussperren.
    for _ in range(10):
        assert await ul.check_and_increment_ai_usage("", limit=1) is True


# ----------------------------------------------------------------------
# Vision-Minuten
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vision_minuten_werden_aufaddiert(db):
    ergebnisse = [await ul.check_and_increment_vision_minutes("seher", 1.0, limit=3.0)
                  for _ in range(5)]

    assert ergebnisse == [True, True, True, False, False]


@pytest.mark.asyncio
async def test_vision_zaehlt_bruchteile_von_minuten(db):
    """Live-Vision rechnet in 12,5-Sekunden-Schritten. Würde auf ganze Minuten
    gerundet, wäre das Kontingent um ein Vielfaches falsch."""
    for _ in range(4):
        assert await ul.check_and_increment_vision_minutes("seher", 12.5 / 60, limit=1.0) is True

    assert await ul.stand_abfragen("seher", ul.ART_VISION) == pytest.approx(50 / 60)


@pytest.mark.asyncio
async def test_text_und_vision_teilen_sich_kein_budget(db):
    for _ in range(3):
        await ul.check_and_increment_ai_usage("nutzer", limit=3)

    # Das Textbudget ist aufgebraucht, Vision darf davon unberührt bleiben.
    assert await ul.check_and_increment_vision_minutes("nutzer", 1.0, limit=3.0) is True


# ----------------------------------------------------------------------
# Der Punkt der ganzen Änderung
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_limit_greift_auch_ohne_redis(db, monkeypatch):
    """Der Kern: kein Redis, trotzdem ein Limit.

    Vorher war das der Fall, in dem GAR NICHT begrenzt wurde -- und damit die
    teuerste Stelle der Anwendung.
    """
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert await ul.check_and_increment_ai_usage("sparfuchs", limit=2) is True
    assert await ul.check_and_increment_ai_usage("sparfuchs", limit=2) is True
    assert await ul.check_and_increment_ai_usage("sparfuchs", limit=2) is False


@pytest.mark.asyncio
async def test_zaehler_ueberlebt_einen_neustart(db):
    """Der Zaehler darf nicht im Prozessspeicher liegen: sonst haette jeder
    Worker sein eigenes Budget und ein Neustart setzte alles zurueck."""
    for _ in range(3):
        await ul.check_and_increment_ai_usage("dauerhaft", limit=3)

    # Modul neu laden = frischer Prozessspeicher. Der Stand kommt aus der
    # Datenbank und muss deshalb erhalten bleiben.
    import importlib
    importlib.reload(ul)

    assert await ul.check_and_increment_ai_usage("dauerhaft", limit=3) is False


@pytest.mark.asyncio
async def test_gleichzeitige_aufrufe_werden_alle_gezaehlt(db):
    """Zwei getrennte Schritte (lesen, dann schreiben) haetten bei
    gleichzeitigen Anfragen Aufrufe verschluckt -- genau das, was ein Limit
    verhindern soll. Der UPSERT zaehlt in einem Schritt."""
    import asyncio

    await asyncio.gather(*[
        ul.check_and_increment_ai_usage("gleichzeitig", limit=1000)
        for _ in range(20)])

    assert await ul.stand_abfragen("gleichzeitig") == 20


@pytest.mark.asyncio
async def test_bei_gestoerter_datenbank_wird_zugelassen(db):
    """Klemmt die Datenbank, soll ein zahlender Nutzer nicht ausgesperrt
    werden. Das ist der Ausnahmefall -- nicht der Normalzustand."""
    @asynccontextmanager
    async def _kaputt():
        raise RuntimeError("Datenbank nicht erreichbar")
        yield  # pragma: no cover

    with patch("database.get_db_session", _kaputt):
        assert await ul.check_and_increment_ai_usage("nutzer", limit=1) is True
        assert await ul.check_and_increment_vision_minutes("nutzer", 999.0, limit=1.0) is True


# ----------------------------------------------------------------------
# Rückbuchung bei Fehlschlag
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fehlgeschlagener_aufruf_wird_zurueckgebucht(db):
    """Gezählt wird VOR dem KI-Aufruf -- anders liesse sich das Limit durch
    gleichzeitige Anfragen überrennen. Scheitert der Aufruf danach (leeres
    Google-Guthaben, Modell überlastet), hätte der Kunde eine seiner 300
    Anfragen für eine Fehlermeldung bezahlt."""
    await ul.check_and_increment_ai_usage("kunde", limit=300)
    assert await ul.stand_abfragen("kunde") == 1

    await ul.gutschreiben("kunde")

    assert await ul.stand_abfragen("kunde") == 0


@pytest.mark.asyncio
async def test_rueckbuchung_geht_nie_unter_null(db):
    """Sonst sammelte ein Nutzer durch wiederholte Fehlschläge ein Guthaben an
    und hätte im nächsten Monat mehr als 300 Anfragen frei."""
    await ul.check_and_increment_ai_usage("kunde", limit=300)

    for _ in range(5):
        await ul.gutschreiben("kunde")

    assert await ul.stand_abfragen("kunde") == 0


@pytest.mark.asyncio
async def test_rueckbuchung_trifft_die_richtige_art(db):
    await ul.check_and_increment_ai_usage("kunde", limit=300)
    await ul.check_and_increment_vision_minutes("kunde", 5.0, limit=90.0)

    await ul.gutschreiben("kunde", ul.ART_VISION, 5.0)

    assert await ul.stand_abfragen("kunde", ul.ART_TEXT) == 1
    assert await ul.stand_abfragen("kunde", ul.ART_VISION) == 0


# ----------------------------------------------------------------------
# Kartensuche -- der Weg, ueber den Nichtangemeldete KI ausloesen konnten
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_suche_ohne_anmeldung_wird_abgelehnt(db):
    """Der Kern der Luecke: die sprachunabhaengige Suche war der einzige Weg,
    auf dem ein nicht angemeldeter Besucher Gemini-Aufrufe ausloesen konnte --
    ungezaehlt und ungedrosselt."""
    assert await ul.check_and_increment_search_ai("") is False


@pytest.mark.asyncio
async def test_suche_hat_ein_eigenes_kontingent(db):
    """Wer viel sucht, darf nicht seine Deck-Analysen verlieren: die Suche ist
    eine Grundfunktion, Judge und Analyse sind Premium-Funktionen."""
    for _ in range(3):
        assert await ul.check_and_increment_search_ai("sucher", limit=3) is True
    assert await ul.check_and_increment_search_ai("sucher", limit=3) is False

    # Das Textkontingent ist davon voellig unberuehrt.
    assert await ul.check_and_increment_ai_usage("sucher", limit=1) is True


# ----------------------------------------------------------------------
# Aufräumen
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_alte_monate_werden_aufgeraeumt(db):
    async with db() as session:
        for monat in ("2024-01", "2024-02", "2099-01"):
            await session.execute(
                text("INSERT INTO ki_nutzung (benutzername, monat, art, wert) "
                     "VALUES ('alt', :m, 'text', 5)"), {"m": monat})
        await session.commit()

    geloescht = await ul.alte_monate_aufraeumen(behalten=3)

    assert geloescht == 2
    async with db() as session:
        rest = (await session.execute(
            text("SELECT monat FROM ki_nutzung ORDER BY monat"))).scalars().all()
    # Der laufende Monat und alles Neuere bleiben stehen.
    assert "2024-01" not in rest and "2024-02" not in rest
    assert "2099-01" in rest
