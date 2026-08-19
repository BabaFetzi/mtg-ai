"""tests/test_deck_abgleich.py -- Deckliste gegen die eigene Sammlung.

Die Frage, die sich bei jedem neuen Deck stellt: was davon habe ich schon, was
muss ich noch besorgen, was kostet das? Bisher musste man dafür jede Karte von
Hand in der Sammlung suchen.

Läuft gegen eine eigene Datenbank im Arbeitsspeicher -- Tests dürfen nichts in
die echte Sammlung schreiben.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from auth import create_access_token
from database import Base
from main import app

client = TestClient(app)

KARTEN = {
    "sol ring": {"name": "Sol Ring", "image": "bild-sol", "price": "1.50",
                 "type": "Artifact", "cmc": 1.0, "mana_cost": "{1}"},
    "lightning bolt": {"name": "Lightning Bolt", "image": "bild-bolt", "price": "3.00",
                       "type": "Instant", "cmc": 1.0, "mana_cost": "{R}"},
    "mountain": {"name": "Mountain", "image": "bild-berg", "price": "0.10",
                 "type": "Basic Land — Mountain", "cmc": 0.0, "mana_cost": ""},
    "delver of secrets // insectile aberration": {
        "name": "Delver of Secrets // Insectile Aberration", "image": "bild-delver",
        "price": "0.40", "type": "Creature — Human Wizard", "cmc": 1.0, "mana_cost": "{U}",
    },
}


def _auth(benutzer: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': benutzer})}"}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _session_patch(maker):
    @asynccontextmanager
    async def _get():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get


async def _lege_an(maker, benutzer, namen):
    async with maker() as session:
        for name in namen:
            await session.execute(
                text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, "
                     "bild_url, preis) VALUES (:u, :n, 'Standard', '', '0.00')"),
                {"u": benutzer, "n": name},
            )
        await session.commit()


async def fake_fetch(namen):
    return {n.lower().strip(): KARTEN[n.lower().strip()]
            for n in namen if n.lower().strip() in KARTEN}


def _abgleich(maker, deck, benutzer="tester"):
    with patch("routers.decks.get_db_session", _session_patch(maker)), \
         patch("routers.decks.fetch_card_details_cached", fake_fetch):
        antwort = client.post("/api/deck/abgleich", json={"deck_liste": deck},
                              headers=_auth(benutzer))
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


@pytest.mark.asyncio
async def test_vorhandene_und_fehlende_karten(db):
    await _lege_an(db, "tester", ["Sol Ring", "Lightning Bolt", "Lightning Bolt"])

    daten = _abgleich(db, "1 Sol Ring\n4 Lightning Bolt")
    sol = next(k for k in daten["karten"] if k["name"] == "Sol Ring")
    bolt = next(k for k in daten["karten"] if k["name"] == "Lightning Bolt")

    assert sol["vorhanden"] == 1 and sol["fehlt"] == 0
    assert bolt["benoetigt"] == 4 and bolt["vorhanden"] == 2 and bolt["fehlt"] == 2
    assert daten["fehlend"] == 2
    # Zwei fehlende Bolts à 3,00.
    assert daten["fehlender_wert"] == "6.00"


@pytest.mark.asyncio
async def test_mehr_exemplare_als_noetig_zaehlen_nicht_doppelt(db):
    await _lege_an(db, "tester", ["Sol Ring"] * 5)

    daten = _abgleich(db, "1 Sol Ring")

    assert daten["karten"][0]["vorhanden"] == 1
    assert daten["vorhanden"] == 1


@pytest.mark.asyncio
async def test_standardlaender_werden_getrennt_ausgewiesen(db):
    """Standardländer bekommt man nachgeworfen. Sie als 'fehlende Karten im
    Wert von X' zu führen, wäre irreführend."""
    daten = _abgleich(db, "24 Mountain\n4 Lightning Bolt")

    assert daten["standardlaender_fehlend"] == 24
    assert daten["fehlend"] == 4
    assert daten["fehlender_wert"] == "12.00"


@pytest.mark.asyncio
async def test_doppelseitige_karte_wird_wiedererkannt(db):
    """In der Sammlung steht oft nur die Vorderseite, in der Deckliste der
    volle Name -- ohne Angleichung gälte dieselbe Karte als nicht vorhanden."""
    await _lege_an(db, "tester", ["Delver of Secrets"])

    daten = _abgleich(db, "1 Delver of Secrets // Insectile Aberration")

    assert daten["karten"][0]["vorhanden"] == 1
    assert daten["karten"][0]["fehlt"] == 0


@pytest.mark.asyncio
async def test_fremde_sammlung_wird_nicht_mitgezaehlt(db):
    await _lege_an(db, "jemand-anderes", ["Sol Ring", "Sol Ring"])

    daten = _abgleich(db, "2 Sol Ring")

    assert daten["karten"][0]["vorhanden"] == 0
    assert daten["karten"][0]["fehlt"] == 2


@pytest.mark.asyncio
async def test_platzhalter_leerer_ordner_zaehlt_nicht_als_karte(db):
    """Leere Ordner werden mit einer Platzhalterzeile angelegt. Die darf nicht
    als Karte im Bestand auftauchen."""
    await _lege_an(db, "tester", ["__PLACEHOLDER__"])

    daten = _abgleich(db, "1 Sol Ring")

    assert daten["vorhanden"] == 0


@pytest.mark.asyncio
async def test_leere_liste_stuerzt_nicht_ab(db):
    daten = _abgleich(db, "")

    assert daten["karten"] == []
    assert daten["fehlender_wert"] == "0.00"


def test_ohne_anmeldung_kein_zugriff():
    antwort = client.post("/api/deck/abgleich", json={"deck_liste": "1 Sol Ring"})
    assert antwort.status_code in (401, 403)


# ======================================================================
# Der fehlende Wert rechnet mit der Auflage
# ----------------------------------------------------------------------
# Sonst stünden auf der Analyseseite zwei verschieden gerechnete Beträge:
# der Deckwert mit der gewählten Auflage, der Fehlbetrag mit dem Standarddruck.
# Bei einem Alpha-Bolt ist das der Unterschied zwischen 3,44 € und 818 €.
# ======================================================================
from services.bestand import abgleichen as _abgleichen, bedarf_aus_deck as _bedarf

_NAMEN = {"lightning bolt": {"name": "Lightning Bolt", "image": "bild-standard",
                             "price": "1.72", "prices": {"eur": "1.72"}}}
_DRUCKE = {
    "lea/161": {"name": "Lightning Bolt", "image": "bild-lea", "price": "409.41"},
    "msc/806": {"name": "Lightning Bolt", "image": "bild-msc", "price": "1.72"},
}


def _zeile(anzahl, set_code=None, nummer=None):
    return {"count": anzahl, "name": "Lightning Bolt", "sideboard": False,
            "set": set_code, "sammlernummer": nummer}


def test_fehlbetrag_nutzt_den_preis_der_gewaehlten_auflage():
    ergebnis = _abgleichen(_bedarf([_zeile(4, "lea", "161")], _NAMEN, _DRUCKE),
                           {"lightning bolt": 2})
    assert ergebnis["fehlend"] == 2
    assert ergebnis["fehlender_wert"] == "818.82"


def test_ohne_auflage_bleibt_der_standarddruck():
    ergebnis = _abgleichen(_bedarf([_zeile(4)], _NAMEN, {}), {"lightning bolt": 2})
    assert ergebnis["fehlender_wert"] == "3.44"


def test_nicht_aufloesbare_auflage_faellt_auf_den_standarddruck_zurueck():
    ergebnis = _abgleichen(_bedarf([_zeile(4, "zzz", "999")], _NAMEN, _DRUCKE),
                           {"lightning bolt": 2})
    assert ergebnis["fehlender_wert"] == "3.44"


def test_zwei_auflagen_derselben_karte_werden_einzeln_bepreist():
    """Vier Bolts, davon zwei aus Alpha -- und zwei liegen schon im Regal.

    Ein einziger Preis je Kartenname könnte hier nur noch schätzen. Gezählt
    wird deshalb je Zeile: die vorhandenen decken die vorderen Zeilen ab, der
    Rest kostet, was SEINE Zeile kostet.
    """
    bedarf = _bedarf([_zeile(2, "msc", "806"), _zeile(2, "lea", "161")], _NAMEN, _DRUCKE)
    ergebnis = _abgleichen(bedarf, {"lightning bolt": 2})

    assert ergebnis["benoetigt"] == 4
    assert ergebnis["fehlend"] == 2
    # Die beiden vorhandenen decken die MSC-Zeile; es fehlen die zwei aus Alpha.
    assert ergebnis["fehlender_wert"] == "818.82"


def test_bild_stammt_von_der_auflage():
    bedarf = _bedarf([_zeile(4, "lea", "161")], _NAMEN, _DRUCKE)
    assert bedarf["lightning bolt"]["bild"] == "bild-lea"


def test_posten_verlassen_die_antwort_nicht():
    """'posten' ist Zwischenrechnung, kein Teil der Schnittstelle."""
    karten = _abgleichen(_bedarf([_zeile(4, "lea", "161")], _NAMEN, _DRUCKE),
                         {})["karten"]
    assert "posten" not in karten[0]
    assert "info" not in karten[0]
