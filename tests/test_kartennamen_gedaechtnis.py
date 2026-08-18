"""Das dauerhafte Gedächtnis für bestätigte Kartennamen.

Warum es das gibt: Die sprachunabhängige Suche kostet bis zu zwei
Gemini-Aufrufe. Ihr Ergebnis lag bisher im Kartencache -- mit 24 Stunden
Verfallszeit. Danach wurde dieselbe Übersetzung erneut gekauft, jeden Tag, für
einen Zusammenhang, der sich nie ändert.

Warum man das behalten DARF, ist der eigentliche Punkt: Hier landet nur, was
vorher gegen Scryfall bestätigt wurde. Das ist ein nachgeschlagener Fakt, keine
Modellmeinung. Für alles, was man nicht nachprüfen kann (eine Deck-Analyse
etwa), gibt es bewusst kein Gedächtnis.

Diese Tests laufen gegen eine ECHTE Datenbank, nicht gegen die Attrappe aus
conftest.py -- sonst wäre genau die Ablage ungetestet, um die es hier geht.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
import services.kartennamen_gedaechtnis as gedaechtnis


@pytest_asyncio.fixture
async def db(leeres_kartennamen_gedaechtnis):
    """Echte SQLite-Datenbank im Speicher.

    `leeres_kartennamen_gedaechtnis` wird angefordert, damit die Attrappe aus
    conftest.py eingerichtet IST -- und hier gezielt wieder durch die echten
    Funktionen ersetzt werden kann.
    """
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

    # Die echten Funktionen zurückholen, die conftest.py durch eine Attrappe
    # ersetzt hat -- hier soll ja gerade die Datenbankfassung laufen.
    import importlib
    frisch = importlib.reload(gedaechtnis)

    with patch("database.get_db_session", _sitzung):
        yield frisch

    await engine.dispose()


# ----------------------------------------------------------------------
# Merken und wiederfinden
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bestaetigter_name_wird_wiedergefunden(db):
    assert await db.merken("Steinstimmen-Goblins", "Stony-Voiced Goblins") is True

    assert await db.nachschlagen("Steinstimmen-Goblins") == "Stony-Voiced Goblins"


@pytest.mark.asyncio
async def test_gross_klein_und_leerzeichen_sind_egal(db):
    await db.merken("  Steinstimmen-Goblins  ", "Stony-Voiced Goblins")

    assert await db.nachschlagen("STEINSTIMMEN-GOBLINS") == "Stony-Voiced Goblins"


@pytest.mark.asyncio
async def test_unbekanntes_ergibt_none(db):
    assert await db.nachschlagen("gibt es nicht") is None


@pytest.mark.asyncio
async def test_der_eintrag_verfaellt_nicht(db):
    """Der ganze Zweck. Ein Cache mit Verfallszeit hatte genau das nicht --
    und liess dieselbe Uebersetzung taeglich neu bezahlen."""
    await db.merken("Blitzschlag", "Lightning Bolt")

    # Es gibt keine Verfallsspalte, an der jemand drehen koennte -- das IST die
    # Zusicherung. Eine solche Spalte nachzuruesten muss diesen Test brechen.
    from database import KartennameGedaechtnis
    spalten = set(KartennameGedaechtnis.__table__.columns.keys())
    assert "gueltig_bis" not in spalten and "verfaellt_am" not in spalten
    assert await db.nachschlagen("Blitzschlag") == "Lightning Bolt"


# ----------------------------------------------------------------------
# Was NICHT ins Gedächtnis darf
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ein_fehlschlag_wird_nicht_dauerhaft_gemerkt(db):
    """Dass eine Karte heute nicht gefunden wird, heisst nicht, dass es sie
    morgen nicht gibt: neue Sets erscheinen laufend, und Scryfall traegt
    lokalisierte Drucke Wochen spaeter nach. Ein dauerhaftes "gibt es nicht"
    wuerde die Karte fuer immer unauffindbar machen."""
    assert await db.merken("Irgendwas Neues", "") is False

    assert await db.nachschlagen("Irgendwas Neues") is None


@pytest.mark.asyncio
async def test_leere_eingabe_wird_nicht_gemerkt(db):
    assert await db.merken("", "Lightning Bolt") is False
    assert await db.merken("   ", "Lightning Bolt") is False


@pytest.mark.asyncio
async def test_identische_eingabe_wird_nicht_gemerkt(db):
    """Wenn Eingabe und Kartenname gleich sind, hat schon die normale Suche
    getroffen -- die KI-Stufe lief nie, und es gibt nichts zu sparen."""
    assert await db.merken("Lightning Bolt", "Lightning Bolt") is False
    assert await db.merken("lightning bolt", "Lightning Bolt") is False


# ----------------------------------------------------------------------
# Zwei Antworten auf dieselbe Frage
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_der_erste_eintrag_bleibt_und_der_widerspruch_wird_gemeldet(db, caplog):
    """Zwei verschiedene Antworten auf dieselbe Eingabe heissen: eine davon
    ist falsch. Stillschweigend zu ueberschreiben waere die schlechteste
    Variante -- dann wechselte das Ergebnis, ohne dass es jemand merkt."""
    import logging

    await db.merken("Furchterregendes Goblin-Duo", "Fearsome Goblin Pair")

    with caplog.at_level(logging.WARNING):
        assert await db.merken("Furchterregendes Goblin-Duo",
                               "Fearsome Goblin Duo") is False

    assert await db.nachschlagen("Furchterregendes Goblin-Duo") == "Fearsome Goblin Pair"
    assert "Fearsome Goblin Duo" in caplog.text


@pytest.mark.asyncio
async def test_zweimal_dasselbe_ist_kein_widerspruch(db, caplog):
    """Zwei Nutzer koennen denselben Namen gleichzeitig aufloesen. Der zweite
    Schreibvorgang darf daran nicht scheitern und nichts melden."""
    import logging

    await db.merken("Blitzschlag", "Lightning Bolt")

    with caplog.at_level(logging.WARNING):
        assert await db.merken("Blitzschlag", "Lightning Bolt") is False

    assert "bereits als" not in caplog.text


# ----------------------------------------------------------------------
# Nachvollziehbarkeit und Korrektur
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_treffer_werden_gezaehlt(db):
    """Die Zahl, an der man den Nutzen des Gedaechtnisses abliest: so viele
    KI-Anfragen hat es erspart."""
    await db.merken("Blitzschlag", "Lightning Bolt")
    for _ in range(3):
        await db.nachschlagen("Blitzschlag")

    assert (await db.stand())["ersparte_ki_anfragen"] == 3
    assert (await db.stand())["eintraege"] == 1


@pytest.mark.asyncio
async def test_ein_falscher_eintrag_laesst_sich_entfernen(db):
    await db.merken("Blitzschlag", "Falsche Karte")

    assert await db.vergessen("Blitzschlag") is True
    assert await db.nachschlagen("Blitzschlag") is None
    assert await db.vergessen("Blitzschlag") is False


# ----------------------------------------------------------------------
# Ausfallverhalten
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ohne_datenbank_faellt_die_suche_nur_zurueck(db):
    """Eine klemmende Datenbank darf die Suche nicht lahmlegen. Ohne
    Gedaechtnis ist sie langsamer und teurer -- aber nicht kaputt."""
    @asynccontextmanager
    async def _kaputt():
        raise RuntimeError("Datenbank weg")
        yield

    with patch("database.get_db_session", _kaputt):
        assert await db.nachschlagen("Blitzschlag") is None
        assert await db.merken("Blitzschlag", "Lightning Bolt") is False
        assert await db.stand() == {"eintraege": 0, "ersparte_ki_anfragen": 0}


# ----------------------------------------------------------------------
# Keine personenbezogenen Daten
# ----------------------------------------------------------------------

def test_die_tabelle_kennt_keinen_benutzernamen():
    """Das Gedaechtnis gilt fuer alle gemeinsam: wer einen Namen einmal
    aufloest, erspart ihn allen anderen. Ein Benutzername waere hier nicht nur
    unnoetig, er wuerde die Tabelle auch zu Kontodaten machen -- und eine
    Kontoloeschung wuerde Wissen mitnehmen, das niemandem gehoert."""
    from database import KartennameGedaechtnis

    assert "benutzername" not in KartennameGedaechtnis.__table__.columns.keys()
