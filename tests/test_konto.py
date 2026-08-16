"""tests/test_konto.py -- Auskunft und Löschung des eigenen Kontos.

Zwei Pflichten aus der DSGVO, die es bisher gar nicht gab: Artikel 20
(Datenübertragbarkeit) und Artikel 17 (Löschung). Ohne beides darf eine Seite
mit echten Kunden nicht starten.

Der heikle Teil ist die Vollständigkeit: bleibt eine Tabelle zurück, sind die
Daten eben NICHT gelöscht. Deshalb prüft ein Test, dass nach der Löschung in
keiner Tabelle mehr etwas steht -- gegen dieselbe Liste, aus der auch der Code
arbeitet.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from auth import create_access_token, hash_passwort
from database import Base
from main import app
from services.konto import NUTZER_TABELLEN, loesche_nutzerdaten, sammle_nutzerdaten

client = TestClient(app)

PASSWORT = "Mein-Passwort-123"


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
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle, email, "
                 "stripe_customer_id, stripe_subscription_id) "
                 "VALUES ('anna', :hash, 'premium', 'anna@example.invalid', 'cus_1', 'sub_1')"),
            {"hash": hash_passwort(PASSWORT)},
        )
        # Ein zweites Konto, das unberührt bleiben muss.
        await s.execute(
            text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) "
                 "VALUES ('bert', :hash, 'free')"),
            {"hash": hash_passwort(PASSWORT)},
        )
        for benutzer in ("anna", "bert"):
            await s.execute(
                text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, "
                     "bild_url, preis) VALUES (:u, 'Sol Ring', 'Standard', '', '1.50')"),
                {"u": benutzer})
            await s.execute(
                text("INSERT INTO decks (benutzername, name, liste, format) "
                     "VALUES (:u, 'Deck', '1 Sol Ring', 'commander')"), {"u": benutzer})
            await s.execute(
                text("INSERT INTO sessions (id, benutzername, refresh_token, laeuft_ab) "
                     "VALUES (:id, :u, :t, '2099-01-01')"),
                {"id": f"sitzung-{benutzer}", "u": benutzer, "t": f"token-{benutzer}"})
            await s.execute(
                text("INSERT INTO passwort_resets (benutzername, token_hash, laeuft_ab) "
                     "VALUES (:u, :t, '2099-01-01')"),
                {"u": benutzer, "t": f"hash-{benutzer}"})
            await s.execute(
                text("INSERT INTO ai_calls (benutzername, funktion, modell, frage) "
                     "VALUES (:u, 'judge', 'test', 'Wie funktioniert Trample?')"), {"u": benutzer})
            await s.execute(
                text("INSERT INTO ki_nutzung (benutzername, monat, art, wert) "
                     "VALUES (:u, '2026-08', 'text', 7)"), {"u": benutzer})
            # Steht in TABELLEN_NUR_LOESCHEN: wird gelöscht, aber nicht
            # ausgehändigt (die IP kann die eines Angreifers sein).
            await s.execute(
                text("INSERT INTO anmeldeversuche (ip, benutzername, versuche, "
                     "gesperrt_bis, zuletzt) VALUES ('1.2.3.4', :u, 2, 0, 0)"),
                {"u": benutzer})
        await s.commit()

    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def zaehler_zuruecksetzen():
    """Die Löschung ist auf 5 Versuche pro Stunde begrenzt -- richtig so, aber
    die Tests laufen alle von derselben Adresse und würden sich sonst
    gegenseitig aussperren.

    Ebenso die Sperrliste gelöschter Konten: sie lebt im Prozess weiter und
    würde die folgenden Tests mit demselben Benutzernamen aussperren.
    """
    from services import sperrliste
    from services.limiter import limiter
    try:
        limiter.reset()
    except Exception:
        pass
    sperrliste.zuruecksetzen()
    yield
    sperrliste.zuruecksetzen()


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


def _export(maker, benutzer="anna"):
    with patch("routers.konto.get_db_session", _session_patch(maker)):
        return client.get("/api/konto/export", headers=_auth(benutzer))


def _loeschen(maker, benutzer="anna", **nutzlast):
    daten = {"passwort": PASSWORT, "bestaetigung": "LÖSCHEN", **nutzlast}
    with patch("routers.konto.get_db_session", _session_patch(maker)):
        return client.post("/api/konto/loeschen", json=daten, headers=_auth(benutzer))


# ----------------------------------------------------------------------
# Auskunft (Artikel 15/20)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_export_enthaelt_alle_bereiche(db):
    antwort = _export(db)
    assert antwort.status_code == 200
    assert "attachment" in antwort.headers["content-disposition"]

    daten = antwort.json()
    assert daten["konto"]["benutzername"] == "anna"
    assert daten["konto"]["email"] == "anna@example.invalid"
    assert len(daten["sammlung_alben"]) == 1
    assert len(daten["decks"]) == 1
    assert daten["ai_calls"][0]["frage"] == "Wie funktioniert Trample?"


@pytest.mark.asyncio
async def test_export_gibt_keine_geheimnisse_heraus(db):
    """Der Passwort-Hash und Sicherheits-Token sagen nichts über die Person aus
    und wären in fremder Hand ein Risiko."""
    text_antwort = _export(db).text

    assert "passwort_hash" not in text_antwort
    assert "token_hash" not in text_antwort
    assert "refresh_token" not in text_antwort
    assert "token-anna" not in text_antwort


@pytest.mark.asyncio
async def test_export_enthaelt_nur_eigene_daten(db):
    daten = _export(db).json()

    alle = str(daten)
    assert "bert" not in alle


def test_export_ohne_anmeldung_gesperrt():
    assert client.get("/api/konto/export").status_code in (401, 403)


# ----------------------------------------------------------------------
# Löschung (Artikel 17)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_loeschung_entfernt_wirklich_alles(db):
    antwort = _loeschen(db)
    assert antwort.status_code == 200, antwort.text

    async with db() as s:
        for tabelle, spalte in NUTZER_TABELLEN:
            anzahl = (await s.execute(
                text(f"SELECT COUNT(*) FROM {tabelle} WHERE {spalte} = 'anna'"))).scalar()
            assert anzahl == 0, f"in {tabelle} sind noch Daten von anna"
        assert (await s.execute(
            text("SELECT COUNT(*) FROM nutzer WHERE benutzername = 'anna'"))).scalar() == 0


@pytest.mark.asyncio
async def test_fremde_daten_bleiben_unberuehrt(db):
    _loeschen(db)

    async with db() as s:
        for tabelle, spalte in NUTZER_TABELLEN:
            anzahl = (await s.execute(
                text(f"SELECT COUNT(*) FROM {tabelle} WHERE {spalte} = 'bert'"))).scalar()
            assert anzahl == 1, f"in {tabelle} fehlen Daten von bert"


@pytest.mark.asyncio
async def test_loeschung_entfernt_auch_die_anmeldeversuche(db):
    """Sie stehen in TABELLEN_NUR_LOESCHEN und wuerden sonst uebersehen:
    zurueck bliebe ein Benutzername samt IP-Adressen."""
    _loeschen(db)

    async with db() as s:
        rest = (await s.execute(text(
            "SELECT COUNT(*) FROM anmeldeversuche WHERE benutzername = 'anna'"))).scalar()
        assert rest == 0
        # Und die des anderen Nutzers bleiben stehen.
        assert (await s.execute(text(
            "SELECT COUNT(*) FROM anmeldeversuche WHERE benutzername = 'bert'"))).scalar() == 1


@pytest.mark.asyncio
async def test_auskunft_gibt_keine_fremden_ip_adressen_heraus(db):
    """Anmeldeversuche verknuepfen einen Benutzernamen mit IP-Adressen -- nicht
    zwingend denen des Kontoinhabers. Wer fremde Zugaenge durchprobiert,
    hinterlaesst SEINE Adresse unter dem angegriffenen Namen. Diese Zeilen
    auszuhaendigen hiesse, Daten Dritter offenzulegen."""
    daten = _export(db).json()

    assert "anmeldeversuche" not in daten
    assert "1.2.3.4" not in str(daten)


@pytest.mark.asyncio
async def test_auskunft_enthaelt_den_ki_verbrauch(db):
    """Der Monatsverbrauch gehoert zum Konto und sagt etwas ueber die Nutzung
    aus -- er muss in der Auskunft stehen."""
    daten = _export(db).json()

    assert daten.get("ki_nutzung"), "KI-Verbrauch fehlt in der Auskunft"
    assert daten["ki_nutzung"][0]["wert"] == 7


@pytest.mark.asyncio
async def test_falsches_passwort_loescht_nichts(db):
    """Ein gestohlenes Zugriffstoken allein darf keine Sammlung vernichten."""
    antwort = _loeschen(db, passwort="falsch")
    assert antwort.status_code == 403

    async with db() as s:
        assert (await s.execute(
            text("SELECT COUNT(*) FROM nutzer WHERE benutzername = 'anna'"))).scalar() == 1


@pytest.mark.asyncio
async def test_ohne_bestaetigungswort_passiert_nichts(db):
    antwort = _loeschen(db, bestaetigung="ja")
    assert antwort.status_code == 400

    async with db() as s:
        assert (await s.execute(
            text("SELECT COUNT(*) FROM sammlung_alben WHERE benutzername = 'anna'"))).scalar() == 1


@pytest.mark.asyncio
async def test_laufendes_abo_wird_beendet(db):
    with patch("stripe.Subscription.delete") as beenden:
        antwort = _loeschen(db)

    beenden.assert_called_once_with("sub_1")
    assert antwort.json()["abo_beendet"] is True


@pytest.mark.asyncio
async def test_loeschung_gelingt_auch_wenn_stripe_streikt(db):
    """Das Recht auf Löschung hängt nicht daran, ob ein fremder Dienst gerade
    erreichbar ist. Der Fehlschlag wird gemeldet, nicht verschwiegen."""
    with patch("stripe.Subscription.delete", side_effect=RuntimeError("Stripe weg")):
        antwort = _loeschen(db)

    assert antwort.status_code == 200
    assert antwort.json()["abo_beendet"] is False
    assert "von Hand" in antwort.json()["abo_hinweis"]

    async with db() as s:
        assert (await s.execute(
            text("SELECT COUNT(*) FROM nutzer WHERE benutzername = 'anna'"))).scalar() == 0


def test_loeschung_ohne_anmeldung_gesperrt():
    antwort = client.post("/api/konto/loeschen",
                          json={"passwort": PASSWORT, "bestaetigung": "LÖSCHEN"})
    assert antwort.status_code in (401, 403)


# ----------------------------------------------------------------------
# Die Tabellenliste selbst
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tabellenliste_deckt_alle_nutzertabellen_ab():
    """Kommt eine Tabelle mit Nutzerbezug dazu und wird hier vergessen, bleiben
    nach einer Löschung Daten zurück -- und niemand merkt es. Deshalb wird die
    Liste gegen das Datenbankmodell geprüft."""
    aus_modell = set()
    for tabelle in Base.metadata.tables.values():
        for spalte in tabelle.columns:
            if spalte.name == "benutzername":
                aus_modell.add(tabelle.name)

    from services.konto import TABELLEN_NUR_LOESCHEN, TABELLEN_OHNE_LOESCHUNG
    gepflegt = ({t for t, _ in NUTZER_TABELLEN}
                | {t for t, _ in TABELLEN_NUR_LOESCHEN}
                | {"nutzer"} | TABELLEN_OHNE_LOESCHUNG)
    fehlend = aus_modell - gepflegt
    assert not fehlend, f"Diese Tabellen fehlen in NUTZER_TABELLEN: {fehlend}"


@pytest.mark.asyncio
async def test_sammeln_und_loeschen_arbeiten_gegen_dieselbe_liste(db):
    """Was die Auskunft zeigt, muss die Löschung auch entfernen."""
    async with db() as s:
        daten = await sammle_nutzerdaten(s, "anna")
        nicht_leer = {t for t, _ in NUTZER_TABELLEN if daten.get(t)}

        geloescht = await loesche_nutzerdaten(s, "anna")
        await s.commit()

    for tabelle in nicht_leer:
        assert geloescht.get(tabelle, 0) > 0, f"{tabelle} wurde ausgewiesen, aber nicht gelöscht"


# ----------------------------------------------------------------------
# Token nach der Löschung
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_token_gilt_nach_der_loeschung_nicht_mehr(db):
    """Token werden beim Prüfen nur entschlüsselt, nicht gegen die Datenbank
    gehalten. Ohne Sperrvermerk könnte ein gelöschtes Konto mit dem alten
    Auffrischungs-Token noch 30 Tage lang neue Zugriffstoken holen -- und dabei
    Daten anlegen, die es laut Löschung nicht mehr geben darf."""
    _loeschen(db)

    with patch("routers.konto.get_db_session", _session_patch(db)):
        # Dasselbe Token wie vorher -- es ist rechnerisch noch gültig.
        antwort = client.get("/api/konto/export", headers=_auth("anna"))

    assert antwort.status_code == 401
    assert "gelöscht" in antwort.json()["detail"]


@pytest.mark.asyncio
async def test_andere_konten_bleiben_angemeldet(db):
    """Die Sperre darf nur das gelöschte Konto treffen."""
    _loeschen(db)

    with patch("routers.konto.get_db_session", _session_patch(db)):
        antwort = client.get("/api/konto/export", headers=_auth("bert"))

    assert antwort.status_code == 200


@pytest.mark.asyncio
async def test_sperrvermerk_wird_geschrieben(db):
    _loeschen(db)

    async with db() as s:
        namen = [r[0] for r in (await s.execute(
            text("SELECT benutzername FROM geloeschte_konten"))).fetchall()]

    assert namen == ["anna"]
