"""tests/test_deck_auflagen.py -- Welche Version einer Karte steckt im Deck?

Gewünscht: "Derzeit kann man ja beim Deckbau nicht auswählen welche Version man
von einer Karte hat und ins Deck baut."

Gespeichert wird die Auflage in der Deckliste selbst ("4x Lightning Bolt (2XM)
123") -- kein zweiter Speicherort, und die Liste bleibt bei Moxfield, Arena und
MTGO einfügbar.

Geprüft wird hier der Weg durch die Endpunkte: dass die Auswahl wirklich in der
Datenbank landet, dass sie fremde Decks nicht anfassen kann und dass Bild und
Preis danach zur gewählten Auflage gehören statt zum Standarddruck.
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

# Standarddruck (über den Namen) und zwei konkrete Auflagen -- mit deutlich
# verschiedenen Preisen, damit ein Rückfall auf den Standarddruck auffällt.
STANDARD = {
    "lightning bolt": {"name": "Lightning Bolt", "image": "bild-standard", "price": "3.00",
                       "type": "Instant", "cmc": 1.0, "colors": ["R"], "set": "m10",
                       "prices": {"eur": "3.00"}},
}

DRUCKE = {
    "2xm/123": {"name": "Lightning Bolt", "image": "bild-2xm", "price": "1.20",
                "type": "Instant", "cmc": 1.0, "set": "2xm", "set_name": "Double Masters",
                "sammlernummer": "123", "scryfall_id": "id-2xm", "prices": {"eur": "1.20"}},
    "lea/161": {"name": "Lightning Bolt", "image": "bild-lea", "price": "480.00",
                "type": "Instant", "cmc": 1.0, "set": "lea", "set_name": "Limited Edition Alpha",
                "sammlernummer": "161", "scryfall_id": "id-lea", "prices": {"eur": "480.00"}},
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
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("INSERT INTO decks (id, benutzername, name, liste, format) "
                 "VALUES (1, 'tester', 'Burn', '4x Lightning Bolt', 'modern')"))
        await s.execute(
            text("INSERT INTO decks (id, benutzername, name, liste, format) "
                 "VALUES (2, 'jemand-anderes', 'Fremd', '4x Lightning Bolt', 'modern')"))
        await s.commit()
    yield maker
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


async def _fake_namen(namen):
    return {n.lower().strip(): STANDARD[n.lower().strip()]
            for n in namen if n.lower().strip() in STANDARD}


async def _fake_drucke(eintraege):
    from services.auflagen import auflage_schluessel
    gefunden = {}
    for e in eintraege or []:
        s = auflage_schluessel(e.get("set"), e.get("sammlernummer"))
        if s in DRUCKE:
            gefunden[s] = DRUCKE[s]
    return gefunden


def _rufe(maker, pfad, nutzlast, benutzer="tester"):
    with patch("routers.decks.get_db_session", _session_patch(maker)):
        return client.post(pfad, json=nutzlast, headers=_auth(benutzer))


async def _liste(maker, deck_id=1):
    async with maker() as s:
        return (await s.execute(
            text("SELECT liste FROM decks WHERE id = :id"), {"id": deck_id})).scalar()


# ----------------------------------------------------------------------
# Auflage wählen
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auflage_landet_in_der_deckliste(db):
    antwort = _rufe(db, "/api/deck/auflage", {
        "deck_id": 1, "card_name": "Lightning Bolt", "set": "2xm", "sammlernummer": "123"})

    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["erfolg"] is True
    assert await _liste(db) == "4x Lightning Bolt (2XM) 123"


@pytest.mark.asyncio
async def test_auflage_wieder_abwaehlen(db):
    _rufe(db, "/api/deck/auflage", {"deck_id": 1, "card_name": "Lightning Bolt",
                                    "set": "2xm", "sammlernummer": "123"})
    _rufe(db, "/api/deck/auflage", {"deck_id": 1, "card_name": "Lightning Bolt",
                                    "alt_set": "2xm", "alt_sammlernummer": "123"})
    assert await _liste(db) == "4x Lightning Bolt"


@pytest.mark.asyncio
async def test_karte_nicht_im_deck(db):
    antwort = _rufe(db, "/api/deck/auflage", {
        "deck_id": 1, "card_name": "Sol Ring", "set": "c21", "sammlernummer": "263"})
    daten = antwort.json()
    assert daten["erfolg"] is False
    assert "Sol Ring" in daten["error"]
    assert await _liste(db) == "4x Lightning Bolt"


@pytest.mark.asyncio
async def test_fremdes_deck_bleibt_unangetastet(db):
    """Der Endpunkt bekommt eine deck_id -- ohne Besitzprüfung könnte damit
    jeder angemeldete Nutzer in fremden Decks herumschreiben."""
    antwort = _rufe(db, "/api/deck/auflage", {
        "deck_id": 2, "card_name": "Lightning Bolt", "set": "2xm", "sammlernummer": "123"})

    assert antwort.json() == {"erfolg": False, "error": "Kein Zugriff auf dieses Deck."}
    assert await _liste(db, 2) == "4x Lightning Bolt"


@pytest.mark.asyncio
async def test_ueberlanger_set_code_wird_abgewiesen(db):
    """Der Wert wird direkt in die Deckliste des Nutzers geschrieben."""
    antwort = _rufe(db, "/api/deck/auflage", {
        "deck_id": 1, "card_name": "Lightning Bolt", "set": "x" * 50})
    assert antwort.status_code == 422
    assert await _liste(db) == "4x Lightning Bolt"


# ----------------------------------------------------------------------
# Hinzufügen und Entfernen mit Auflage
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_zweite_auflage_bekommt_eine_eigene_zeile(db):
    _rufe(db, "/api/deck/auflage", {"deck_id": 1, "card_name": "Lightning Bolt",
                                    "set": "2xm", "sammlernummer": "123"})
    _rufe(db, "/api/deck/add-card", {"deck_id": 1, "card_name": "Lightning Bolt",
                                     "set": "lea", "sammlernummer": "161"})

    assert await _liste(db) == "4x Lightning Bolt (2XM) 123\n1x Lightning Bolt (LEA) 161"


@pytest.mark.asyncio
async def test_entfernen_trifft_die_gewaehlte_auflage(db):
    _rufe(db, "/api/deck/auflage", {"deck_id": 1, "card_name": "Lightning Bolt",
                                    "set": "2xm", "sammlernummer": "123"})
    _rufe(db, "/api/deck/add-card", {"deck_id": 1, "card_name": "Lightning Bolt",
                                     "set": "lea", "sammlernummer": "161"})
    _rufe(db, "/api/deck/remove-card", {"deck_id": 1, "card_name": "Lightning Bolt",
                                        "set": "lea", "sammlernummer": "161"})

    assert await _liste(db) == "4x Lightning Bolt (2XM) 123"


@pytest.mark.asyncio
async def test_entfernen_meldet_eine_karte_die_nicht_da_ist(db):
    antwort = _rufe(db, "/api/deck/remove-card",
                    {"deck_id": 1, "card_name": "Sol Ring"})
    assert antwort.json()["erfolg"] is False


# ----------------------------------------------------------------------
# Bild und Preis folgen der Auflage
# ----------------------------------------------------------------------
def _visualize(liste):
    with patch("routers.decks.fetch_card_details_cached", _fake_namen), \
         patch("routers.decks.drucke_fuer_deck", _fake_drucke):
        return client.post("/api/deck/visualize", json={"deck_liste": liste},
                           headers=_auth("tester")).json()


def _wert(liste):
    with patch("routers.decks.fetch_card_details_cached", _fake_namen), \
         patch("routers.decks.drucke_fuer_deck", _fake_drucke):
        return client.post("/api/deck/wert", json={"deck_liste": liste},
                           headers=_auth("tester")).json()


def test_bild_und_preis_stammen_von_der_gewaehlten_auflage():
    karte = _visualize("4x Lightning Bolt (LEA) 161")["karten"][0]
    assert karte["image"] == "bild-lea"
    assert karte["price"] == "480.00"
    assert karte["set"] == "lea"
    assert karte["sammlernummer"] == "161"
    assert karte["auflage_gewuenscht"] is True
    assert karte["auflage_gefunden"] is True


def test_ohne_auflage_gilt_der_standarddruck():
    karte = _visualize("4x Lightning Bolt")["karten"][0]
    assert karte["image"] == "bild-standard"
    assert karte["price"] == "3.00"
    assert karte["auflage_gewuenscht"] is False
    assert karte["auflage_gefunden"] is False


def test_nicht_aufloesbare_auflage_wird_als_solche_gemeldet():
    """Keine erfundenen Daten: Wenn die gewählte Auflage nicht auffindbar ist,
    zeigt die Ansicht den Standarddruck -- sagt das aber auch, statt ihn als
    die Wahl des Nutzers auszugeben."""
    karte = _visualize("4x Lightning Bolt (ZZZ) 999")["karten"][0]
    assert karte["image"] == "bild-standard"
    assert karte["auflage_gewuenscht"] is True
    assert karte["auflage_gefunden"] is False
    # Die Angabe des Nutzers bleibt sichtbar, damit die Auswahl nicht wortlos
    # verschwindet.
    assert karte["set"] == "zzz"


def test_deckwert_rechnet_mit_der_auflage():
    """Der eigentliche Grund für das ganze Vorhaben: 4 Bolts sind je nach
    Auflage 4,80 Euro oder 1920 Euro wert."""
    assert _wert("4x Lightning Bolt (2XM) 123")["gesamt_wert"] == "4.80"
    assert _wert("4x Lightning Bolt (LEA) 161")["gesamt_wert"] == "1920.00"
    assert _wert("4x Lightning Bolt")["gesamt_wert"] == "12.00"


def test_gemischte_auflagen_im_selben_deck():
    daten = _visualize("2x Lightning Bolt (2XM) 123\n2x Lightning Bolt (LEA) 161")
    assert [k["image"] for k in daten["karten"]] == ["bild-2xm", "bild-lea"]
    assert _wert("2x Lightning Bolt (2XM) 123\n2x Lightning Bolt (LEA) 161")[
        "gesamt_wert"] == "962.40"


# ----------------------------------------------------------------------
# Auflagen zur Auswahl anbieten -- mit dem eigenen Besitz markiert
# ----------------------------------------------------------------------
AUFLAGEN_VON_SCRYFALL = [
    {"id": "id-2xm", "set": "2xm", "set_name": "Double Masters", "sammlernummer": "123",
     "seltenheit": "rare", "bild_url": "bild-2xm", "preis": "1.20", "preis_foil": "4.00"},
    {"id": "id-lea", "set": "lea", "set_name": "Limited Edition Alpha", "sammlernummer": "161",
     "seltenheit": "common", "bild_url": "bild-lea", "preis": "480.00", "preis_foil": ""},
    {"id": "id-m10", "set": "m10", "set_name": "Magic 2010", "sammlernummer": "146",
     "seltenheit": "common", "bild_url": "bild-m10", "preis": "3.00", "preis_foil": ""},
]


@pytest_asyncio.fixture
async def sammlung():
    """Eine Sammlung mit zwei Bolts aus 2XM und einem ohne erfasste Nummer."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for edition, nummer in [("2xm", "123"), ("2XM", "123"), ("m10", None)]:
            await s.execute(
                text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, "
                     "edition, sammlernummer) VALUES ('tester', 'Lightning Bolt', "
                     "'Standard', :edition, :nummer)"),
                {"edition": edition, "nummer": nummer})
        await s.execute(
            text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, "
                 "edition, sammlernummer) VALUES ('jemand-anderes', 'Lightning Bolt', "
                 "'Standard', 'lea', '161')"))
        await s.commit()
    yield maker
    await engine.dispose()


def _auflagen_abfragen(maker, benutzer="tester"):
    async def _fake_prints(client, daten, fallback):
        return list(AUFLAGEN_VON_SCRYFALL)

    class _Antwort:
        status_code = 200

        @staticmethod
        def json():
            return {"name": "Lightning Bolt", "image_uris": {"normal": "bild-standard"}}

    async def _fake_request(client, methode, url, **kwargs):
        return _Antwort()

    with patch("routers.cards.get_db_session", _session_patch(maker)), \
         patch("routers.cards._fetch_prints", _fake_prints), \
         patch("routers.cards.scryfall_request", _fake_request):
        return client.get("/api/karten/auflagen/Lightning Bolt", headers=_auth(benutzer))


@pytest.mark.asyncio
async def test_auflagen_werden_mit_dem_eigenen_besitz_markiert(sammlung):
    antwort = _auflagen_abfragen(sammlung)

    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    besitz = {a["set"]: a["besitzt"] for a in daten["auflagen"]}
    assert besitz["2xm"] == 2
    # Ein Sammlungseintrag ohne erfasste Sammlernummer zählt für die Edition --
    # sonst erschiene die Auflage als nicht besessen, obwohl die Karte da ist.
    assert besitz["m10"] == 1
    assert besitz["lea"] == 0


@pytest.mark.asyncio
async def test_fremder_besitz_zaehlt_nicht(sammlung):
    """Die Sammlung eines anderen Nutzers darf hier nirgends durchschlagen."""
    antwort = _auflagen_abfragen(sammlung, benutzer="dritter")
    assert all(a["besitzt"] == 0 for a in antwort.json()["auflagen"])
