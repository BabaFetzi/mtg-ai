"""Was vor dem Livegang stimmen muss.

Diese Prüfungen haben nichts mit einer einzelnen Funktion zu tun -- sie halten
fest, wie sich die Anwendung im Betrieb verhält, wenn etwas schiefgeht. Genau
das fällt in der Entwicklung nie auf: lokal ist die Datenbank da, die Dateien
sind klein, und den Fehlertext liest man selbst.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main
from auth import create_access_token


@pytest.fixture
def client():
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


# ======================================================================
# Fehlermeldungen verraten nichts
# ======================================================================
# Der globale Handler lieferte str(exc) an den Client aus. Bei einem
# Datenbankfehler steht dort das SQL samt Tabellen- und Spaltennamen, bei einem
# Dateifehler der Pfad auf dem Server. Das ist eine Bauanleitung für den
# nächsten Angriff -- ausgeliefert an jeden, der einen Fehler provozieren kann.

@pytest.fixture
def kaputter_endpunkt():
    pfad = "/_test_kaputt"

    @main.app.get(pfad)
    async def _kaputt():
        raise RuntimeError("SELECT passwort_hash FROM nutzer WHERE id=42")

    yield pfad
    main.app.router.routes = [r for r in main.app.router.routes
                              if getattr(r, "path", None) != pfad]


def test_in_produktion_wird_die_ursache_nicht_ausgeliefert(
        client, kaputter_endpunkt, monkeypatch):
    monkeypatch.setattr(main, "IST_PRODUKTION", True)

    antwort = client.get(kaputter_endpunkt)
    text = antwort.text

    assert antwort.status_code == 500
    assert "passwort_hash" not in text
    assert "SELECT" not in text
    assert "RuntimeError" not in text


def test_der_nutzer_bekommt_eine_kennung_zum_melden(
        client, kaputter_endpunkt, monkeypatch):
    """Ohne sie kann eine Meldung ("bei mir ging etwas kaputt") keinem Eintrag
    im Protokoll zugeordnet werden -- man müsste raten."""
    monkeypatch.setattr(main, "IST_PRODUKTION", True)

    daten = client.get(kaputter_endpunkt).json()

    assert daten["fehlerkennung"]
    assert daten["fehlerkennung"] in daten["error"]


def test_in_der_entwicklung_steht_die_ursache_dabei(
        client, kaputter_endpunkt, monkeypatch):
    """Beim Entwickeln ist genau das die Angabe, die man braucht."""
    monkeypatch.setattr(main, "IST_PRODUKTION", False)

    daten = client.get(kaputter_endpunkt).json()

    assert "RuntimeError" in daten["details"]


# ======================================================================
# Sicherheitskopfzeilen
# ======================================================================

def test_die_sicherheitskopfzeilen_sind_gesetzt(client):
    kopf = client.get("/health").headers

    assert kopf["X-Frame-Options"] == "DENY"
    assert kopf["X-Content-Type-Options"] == "nosniff"
    assert "strict-origin" in kopf["Referrer-Policy"]
    assert "microphone=()" in kopf["Permissions-Policy"]


def test_hsts_nur_in_produktion(client, monkeypatch):
    """Ein einmal gesetztes HSTS merkt sich der Browser monatelang. Auf
    localhost wäre das eine selbstgebaute Falle."""
    monkeypatch.setattr(main, "IST_PRODUKTION", False)
    assert "Strict-Transport-Security" not in client.get("/health").headers

    monkeypatch.setattr(main, "IST_PRODUKTION", True)
    assert "Strict-Transport-Security" in client.get("/health").headers


def test_die_kamera_bleibt_fuer_die_eigene_seite_erlaubt(client):
    """Live-Vision braucht sie -- eine Kopfzeile, die die eigene Funktion
    abschaltet, wäre schlimmer als keine."""
    assert "camera=(self)" in client.get("/health").headers["Permissions-Policy"]


# ======================================================================
# Health-Check
# ======================================================================
# Er meldete bedingungslos "ok" -- auch mit toter Datenbank. Ein Lastverteiler
# glaubt das und schickt weiter Nutzer auf eine Instanz, die jede Anfrage mit
# einem Fehler beantwortet.

def test_health_meldet_ok_wenn_die_datenbank_da_ist(client):
    antwort = client.get("/health")

    assert antwort.status_code == 200
    assert antwort.json()["datenbank"] is True


def test_health_meldet_fehler_wenn_die_datenbank_weg_ist(client):
    @asynccontextmanager
    async def _keine_datenbank():
        raise RuntimeError("connection refused")
        yield

    with patch("database.get_db_session", _keine_datenbank):
        antwort = client.get("/health")

    assert antwort.status_code == 503, (
        "Ein Lastverteiler muss diese Instanz aus dem Verkehr ziehen können")
    assert antwort.json()["datenbank"] is False


def test_health_verraet_die_ursache_nicht(client):
    """Auch hier gilt: der Grund gehört ins Protokoll, nicht ins Internet."""
    @asynccontextmanager
    async def _keine_datenbank():
        raise RuntimeError("password authentication failed for user 'grana'")
        yield

    with patch("database.get_db_session", _keine_datenbank):
        text = client.get("/health").text

    assert "password" not in text


# ======================================================================
# Grenzen für alles, was von aussen hereinkommt
# ======================================================================
# Weder der CSV-Import noch die beiden Vision-WebSockets hatten eine
# Grössenbegrenzung. `await file.read()` und `receive_bytes()` nehmen
# entgegen, was kommt -- eine einzige grosse Datei genügt, um den
# Arbeitsspeicher des Prozesses zu füllen. Danach ist die Seite für ALLE weg.
#
# Die Drosselung schützt davor nicht: sie begrenzt die ANZAHL der Anfragen,
# nicht ihre Grösse. Bei 10 erlaubten Importen pro Minute reicht einer.

import io

from routers.collection import MAX_CSV_BYTES
from routers.vision import VISION_MAX_BILD_BYTES


def _anmeldung(benutzer="grenztester"):
    # create_access_token wird BEIM MODULIMPORT geholt (oben), nicht hier
    # drin: tests/test_jwt_secret.py laedt das auth-Modul neu, und ein danach
    # frisch geholtes create_access_token signiert mit einem anderen
    # Schluessel als der, gegen den routers/collection.py prueft -- die
    # Anfrage kaeme dann mit HTTP 401 zurueck statt mit 413. Allein bestanden
    # diese Tests, in der vollen Suite nicht.
    return {"Authorization": f"Bearer {create_access_token({'sub': benutzer})}"}


@pytest.fixture
def frische_drosselung():
    """Der Drosselungszaehler gilt prozessweit und ueberlebt einzelne Tests.

    tests/test_drosselung.py schickt selbst Anfragen an denselben Endpunkt
    (10/Minute). Ohne Zuruecksetzen haengt das Ergebnis hier davon ab, welche
    Datei vorher lief -- allein bestanden diese Tests, in der vollen Suite kam
    HTTP 429 statt 413.
    """
    from services.limiter import limiter
    limiter.reset()
    yield
    limiter.reset()


def test_zu_grosse_csv_wird_abgelehnt(client, frische_drosselung):
    zu_gross = io.BytesIO(b"a," * (MAX_CSV_BYTES // 2 + 1024))

    antwort = client.post(
        "/api/sammlung/import-csv",
        files={"file": ("riesig.csv", zu_gross, "text/csv")},
        data={"album_name": "Import"},
        headers=_anmeldung(),
    )

    assert antwort.status_code == 413
    assert "MB" in antwort.json()["detail"]


def test_die_ablehnung_kommt_nicht_als_erfolg_zurueck(client, frische_drosselung):
    """Der bestehende `except Exception` haette die Ablehnung verschluckt und
    daraus HTTP 200 mit erfolg=False gemacht -- der Browser saehe einen
    erfolgreichen Aufruf."""
    zu_gross = io.BytesIO(b"a," * (MAX_CSV_BYTES // 2 + 1024))

    antwort = client.post(
        "/api/sammlung/import-csv",
        files={"file": ("riesig.csv", zu_gross, "text/csv")},
        data={"album_name": "Import"},
        headers=_anmeldung(),
    )

    assert antwort.status_code != 200


def test_die_grenzen_lassen_dem_echten_betrieb_luft():
    """Eine Grenze, die den Normalfall trifft, waere ein neuer Fehler.

    Eine Sammlung mit 100.000 Karten liegt bei etwa 5 MB; MobileCamera.jsx
    schickt rund 300 KB je Bild.
    """
    assert MAX_CSV_BYTES >= 10 * 1024 * 1024
    assert VISION_MAX_BILD_BYTES >= 2 * 1024 * 1024


# ======================================================================
# Das Startskript zeigt auf echte Adressen
# ======================================================================
# start.ps1 startet die Stripe-CLI mit einer fest eingetragenen Webhook-URL.
# Benennt jemand die Route um, laeuft der Start weiterhin durch -- die
# Webhooks landen dann nur im Nichts, und ein Testkauf schaltet still kein
# Premium frei. Das faellt sonst erst auf, wenn ein Kunde sich beschwert.

import re
from pathlib import Path


def _start_skript() -> str:
    return Path(__file__).resolve().parents[1].joinpath("start.ps1").read_text(
        encoding="utf-8")


def test_der_webhook_pfad_im_startskript_existiert_wirklich(client):
    treffer = re.search(r"\$WebhookPfad\s*=\s*'([^']+)'", _start_skript())
    assert treffer, "In start.ps1 steht kein $WebhookPfad mehr"
    pfad = treffer.group(1)

    antwort = client.post(pfad, content=b"{}")

    # 400 = "Signatur fehlt" -- die Route ist da und weist die unsignierte
    # Anfrage zurueck. 404 hiesse: das Startskript zeigt ins Leere.
    assert antwort.status_code != 404, (
        f"start.ps1 leitet Webhooks an {pfad} -- diese Route gibt es nicht")
    assert antwort.status_code == 400


def test_die_ports_im_startskript_passen_zum_frontend(client):
    """Das Frontend spricht das Backend ueber einen fest eingetragenen Port
    an (vite.config.js). Weichen die beiden voneinander ab, laedt die Seite,
    aber jede Anfrage schlaegt fehl."""
    skript = _start_skript()
    backend = re.search(r"\$BackendPort\s*=\s*(\d+)", skript)
    frontend = re.search(r"\$FrontendPort\s*=\s*(\d+)", skript)
    assert backend and frontend

    vite = Path(__file__).resolve().parents[1].joinpath(
        "mtg-frontend/vite.config.js").read_text(encoding="utf-8")

    assert f"127.0.0.1:{backend.group(1)}" in vite, (
        f"start.ps1 startet das Backend auf Port {backend.group(1)}, "
        f"vite.config.js leitet woandershin")
    assert f"port: {frontend.group(1)}" in vite
