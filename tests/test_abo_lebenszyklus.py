"""tests/test_abo_lebenszyklus.py – Der Kauf-Weg von Anfang bis Ende (T-8.3)

Die vorhandenen Stripe-Tests prüfen mit einer nachgebauten Datenbank-Sitzung,
dass ein UPDATE *aufgerufen* wurde. Das genügt hier nicht: Der teuerste
denkbare Fehler ist ein Kauf, der kein Premium freischaltet -- und der würde
sich genau darin zeigen, dass das UPDATE zwar läuft, aber niemanden trifft
(falscher Benutzername, falsche Kunden-ID, falsche Spalte).

Diese Tests laufen deshalb gegen eine echte SQLite-Datenbank mit dem echten
Schema und prüfen den Zustand NACH dem Ereignis.

Abgedeckt ist der vollständige Lebenszyklus:
    Kauf -> Premium -> Kündigung -> Ablauf -> wieder free
sowie Zahlungsausfall und die Frage, ob ein Ereignis fremde Konten berührt.
"""

import hashlib
import hmac
import itertools
import json
import time
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from main import app
from database import Base

client = TestClient(app)

WEBHOOK_SECRET = "whsec_test_lebenszyklus"


@pytest.fixture(autouse=True)
def _webhook_env(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    yield


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, expire_on_commit=False)
    async with macher() as s:
        # Zwei Konten: eines kauft, das andere darf davon NICHTS mitbekommen.
        await s.execute(text(
            "INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES ('kaeufer', 'x', 'free')"))
        await s.execute(text(
            "INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES ('unbeteiligt', 'x', 'free')"))
        await s.commit()
    yield macher
    await engine.dispose()


def _sitzungsfabrik(macher):
    @asynccontextmanager
    async def _get_db_session():
        async with macher() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _get_db_session


def _signiere(rohdaten: bytes) -> str:
    """Baut eine echte Stripe-Signatur -- unsignierte Ereignisse werden
    absichtlich abgelehnt, auch im Test."""
    zeitpunkt = int(time.time())
    signatur = hmac.new(
        WEBHOOK_SECRET.encode(),
        f"{zeitpunkt}.{rohdaten.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={zeitpunkt},v1={signatur}"


_zaehler = itertools.count(1)


def _ereignis(typ: str, objekt: dict, ereignis_id: str = None,
              erstellt: int = None) -> bytes:
    """Ein Stripe-Ereignis. Jedes bekommt standardmaessig eine eigene ID --
    zwei Ereignisse mit derselben ID sind fuer den Webhook (zu Recht) eine
    Wiederholung und werden uebersprungen."""
    return json.dumps({
        "id": ereignis_id or f"evt_{next(_zaehler)}",
        "object": "event", "type": typ,
        "created": erstellt if erstellt is not None else int(time.time()),
        "data": {"object": objekt},
    }).encode()


def _sende(db, typ: str, objekt: dict, ereignis_id: str = None,
           erstellt: int = None):
    rohdaten = _ereignis(typ, objekt, ereignis_id, erstellt)
    with patch("routers.payments.get_db_session", _sitzungsfabrik(db)):
        return client.post(
            "/api/checkout/webhook",
            content=rohdaten,
            headers={"stripe-signature": _signiere(rohdaten), "Content-Type": "application/json"},
        )


async def _zustand(db, name: str) -> dict:
    async with db() as s:
        res = await s.execute(
            text("SELECT rolle, stripe_customer_id, stripe_subscription_id "
                 "FROM nutzer WHERE benutzername = :n"),
            {"n": name},
        )
        return dict(res.mappings().first())


# ----------------------------------------------------------------------
# Der vollständige Lebenszyklus
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kauf_schaltet_premium_wirklich_frei(db):
    """Der teuerste denkbare Fehler: bezahlt, aber kein Premium."""
    assert (await _zustand(db, "kaeufer"))["rolle"] == "free"

    antwort = _sende(db, "checkout.session.completed", {
        "customer": "cus_kaeufer", "subscription": "sub_kaeufer",
        "metadata": {"benutzername": "kaeufer"},
    })
    assert antwort.status_code == 200

    nachher = await _zustand(db, "kaeufer")
    assert nachher["rolle"] == "premium"
    # Ohne gespeicherte Kunden-ID greift später weder Kündigung noch Ablauf.
    assert nachher["stripe_customer_id"] == "cus_kaeufer"
    assert nachher["stripe_subscription_id"] == "sub_kaeufer"


@pytest.mark.asyncio
async def test_abo_ende_stuft_zurueck(db):
    _sende(db, "checkout.session.completed", {
        "customer": "cus_kaeufer", "subscription": "sub_kaeufer",
        "metadata": {"benutzername": "kaeufer"},
    })
    assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"

    antwort = _sende(db, "customer.subscription.deleted", {"customer": "cus_kaeufer"})
    assert antwort.status_code == 200

    nachher = await _zustand(db, "kaeufer")
    assert nachher["rolle"] == "free"
    assert nachher["stripe_subscription_id"] is None


def _kaufen(db):
    _sende(db, "checkout.session.completed", {
        "customer": "cus_kaeufer", "subscription": "sub_kaeufer",
        "metadata": {"benutzername": "kaeufer"},
    })


@pytest.mark.asyncio
async def test_zahlungsausfall_nimmt_nicht_sofort_den_zugang(db):
    """Der erste Fehlversuch darf nicht herabstufen.

    Stripe versucht eine fehlgeschlagene Zahlung noch tagelang erneut, und
    meistens klappt sie. Vorher verlor ein Kunde mit kurz abgelaufener Karte
    sofort seinen Zugang -- obwohl er weiter zahlt -- und bekam ihn NIE
    zurueck, weil das Gegenereignis nicht verarbeitet wurde.
    """
    _kaufen(db)
    _sende(db, "invoice.payment_failed", {"customer": "cus_kaeufer"})

    assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"


@pytest.mark.asyncio
async def test_nach_geglueckter_wiederholung_bleibt_premium(db):
    """Der haeufigste Verlauf: Zahlung scheitert, Stripe probiert es erneut,
    es klappt. Der Kunde darf davon gar nichts merken."""
    _kaufen(db)
    _sende(db, "invoice.payment_failed", {"customer": "cus_kaeufer"})
    _sende(db, "customer.subscription.updated",
           {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "past_due"})
    assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"

    _sende(db, "customer.subscription.updated",
           {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "active"})
    assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"


@pytest.mark.asyncio
async def test_erschoepfte_wiederholungen_stufen_herab(db):
    """Gibt Stripe auf, muss der Zugang weg sein -- sonst zahlt niemand mehr."""
    _kaufen(db)
    _sende(db, "customer.subscription.updated",
           {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "unpaid"})

    assert (await _zustand(db, "kaeufer"))["rolle"] == "free"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,erwartet", [
    ("active", "premium"),
    ("trialing", "premium"),
    ("past_due", "premium"),   # Karenz: Stripe versucht es noch
    ("unpaid", "free"),
    ("canceled", "free"),
    ("incomplete", "free"),
    ("incomplete_expired", "free"),
])
async def test_jeder_abo_status_ergibt_die_richtige_rolle(db, status, erwartet):
    _kaufen(db)
    _sende(db, "customer.subscription.updated",
           {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": status})

    assert (await _zustand(db, "kaeufer"))["rolle"] == erwartet


# ----------------------------------------------------------------------
# Wiederholung und Reihenfolge
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dasselbe_ereignis_zweimal_wird_nur_einmal_verarbeitet(db):
    _kaufen(db)
    erste = _sende(db, "customer.subscription.updated",
                   {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "canceled"},
                   ereignis_id="evt_gleich")
    zweite = _sende(db, "customer.subscription.updated",
                    {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "canceled"},
                    ereignis_id="evt_gleich")

    assert erste.json()["status"] == "success"
    assert zweite.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_ein_verspaetetes_altes_ereignis_nimmt_kein_premium_weg(db):
    """Stripe garantiert KEINE Reihenfolge. Kaeme ein altes "canceled" nach
    einem neuen "active" an, verloere ein zahlender Kunde seinen Zugang --
    ohne dass irgendwo ein Fehler auftaucht."""
    _kaufen(db)
    jetzt = int(time.time())

    _sende(db, "customer.subscription.updated",
           {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "active"},
           erstellt=jetzt)
    antwort = _sende(db, "customer.subscription.updated",
                     {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "canceled"},
                     erstellt=jetzt - 3600)

    assert antwort.json()["status"] == "stale"
    assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"


@pytest.mark.asyncio
async def test_die_reihenfolge_gilt_je_kunde(db):
    """Ein neueres Ereignis eines ANDEREN Kunden darf dieses hier nicht
    blockieren -- sonst haengt das Abo davon ab, wer sonst gerade zahlt."""
    jetzt = int(time.time())
    _sende(db, "customer.subscription.updated",
           {"id": "sub_fremd", "customer": "cus_fremd", "status": "active"},
           erstellt=jetzt)

    _kaufen(db)
    antwort = _sende(db, "customer.subscription.updated",
                     {"id": "sub_kaeufer", "customer": "cus_kaeufer", "status": "canceled"},
                     erstellt=jetzt - 3600)

    assert antwort.json()["status"] == "success"
    assert (await _zustand(db, "kaeufer"))["rolle"] == "free"


@pytest.mark.asyncio
async def test_erneuter_kauf_nach_kuendigung_funktioniert(db):
    """Wer zurückkommt, muss wieder Premium bekommen -- ein häufiger Fall,
    der leicht durchrutscht, weil beim Downgrade Felder geleert werden."""
    for _ in range(2):
        _sende(db, "checkout.session.completed", {
            "customer": "cus_kaeufer", "subscription": "sub_neu",
            "metadata": {"benutzername": "kaeufer"},
        })
        assert (await _zustand(db, "kaeufer"))["rolle"] == "premium"
        _sende(db, "customer.subscription.deleted", {"customer": "cus_kaeufer"})
        assert (await _zustand(db, "kaeufer"))["rolle"] == "free"


# ----------------------------------------------------------------------
# Was NICHT passieren darf
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fremdes_konto_bleibt_unberuehrt(db):
    _sende(db, "checkout.session.completed", {
        "customer": "cus_kaeufer", "subscription": "sub_kaeufer",
        "metadata": {"benutzername": "kaeufer"},
    })
    assert (await _zustand(db, "unbeteiligt"))["rolle"] == "free"

    _sende(db, "customer.subscription.deleted", {"customer": "cus_kaeufer"})
    assert (await _zustand(db, "unbeteiligt"))["rolle"] == "free"


@pytest.mark.asyncio
async def test_wiederholtes_ereignis_aendert_nichts(db):
    """Stripe stellt Ereignisse mehrfach zu, wenn eine Antwort ausbleibt.
    Zweimal dasselbe muss denselben Zustand ergeben."""
    for _ in range(3):
        antwort = _sende(db, "checkout.session.completed", {
            "customer": "cus_kaeufer", "subscription": "sub_kaeufer",
            "metadata": {"benutzername": "kaeufer"},
        })
        assert antwort.status_code == 200

    nachher = await _zustand(db, "kaeufer")
    assert nachher["rolle"] == "premium"
    assert nachher["stripe_customer_id"] == "cus_kaeufer"


@pytest.mark.asyncio
async def test_gefaelschtes_ereignis_vergibt_kein_premium(db):
    """Ohne gültige Signatur darf niemand Premium bekommen -- sonst genügt
    ein POST auf den Webhook, um sich selbst freizuschalten."""
    rohdaten = _ereignis("checkout.session.completed", {
        "customer": "cus_angreifer", "metadata": {"benutzername": "kaeufer"},
    })
    with patch("routers.payments.get_db_session", _sitzungsfabrik(db)):
        antwort = client.post(
            "/api/checkout/webhook",
            content=rohdaten,
            headers={"stripe-signature": "t=1,v1=voellig-erfunden",
                     "Content-Type": "application/json"},
        )

    assert antwort.status_code == 400
    assert (await _zustand(db, "kaeufer"))["rolle"] == "free"


@pytest.mark.asyncio
async def test_ereignis_ohne_benutzernamen_schaltet_niemanden_frei(db):
    """Fehlt die Zuordnung in den Metadaten, darf NICHT geraten werden."""
    antwort = _sende(db, "checkout.session.completed", {
        "customer": "cus_ohne_zuordnung", "subscription": "sub_x", "metadata": {},
    })
    assert antwort.status_code == 200  # Stripe soll nicht erneut zustellen
    assert (await _zustand(db, "kaeufer"))["rolle"] == "free"
    assert (await _zustand(db, "unbeteiligt"))["rolle"] == "free"


@pytest.mark.asyncio
async def test_unbekanntes_ereignis_wird_ruhig_quittiert(db):
    """Stripe schickt viele Ereignistypen. Unbekannte müssen mit 200
    quittiert werden, sonst wiederholt Stripe sie stundenlang."""
    antwort = _sende(db, "customer.subscription.updated", {"customer": "cus_kaeufer"})
    assert antwort.status_code == 200
