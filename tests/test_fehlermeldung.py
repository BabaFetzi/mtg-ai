"""tests/test_fehlermeldung.py -- Fehlerberichte dürfen kein Datenleck sein.

Ohne Überwachung merkt man einen Ausfall erst, wenn sich jemand beschwert. Eine
Überwachung, die Zugangsdaten mitschickt, ist aber schlimmer als keine: sie
trägt Passwörter und Schlüssel zu einem fremden Dienst.

Ebenso wichtig: die App muss ohne Überwachungsdienst laufen. Ein Werkzeug, das
den Start verhindert, wäre die schlechteste aller Möglichkeiten.
"""

import pytest

from services.fehlermeldung import GEHEIME_FELDER, einrichten, vor_dem_senden


# ----------------------------------------------------------------------
# Säubern
# ----------------------------------------------------------------------
def test_kopfzeile_mit_token_wird_entfernt():
    ereignis = {"request": {"headers": {"Authorization": "Bearer geheim123",
                                        "User-Agent": "Firefox"}}}

    sauber = vor_dem_senden(ereignis)

    assert sauber["request"]["headers"]["Authorization"] == "[entfernt]"
    assert sauber["request"]["headers"]["User-Agent"] == "Firefox"


def test_passwoerter_und_schluessel_werden_entfernt():
    ereignis = {"extra": {"passwort": "hunter2", "stripe_secret_key": "sk_live_x",
                          "jwt_secret_key": "abc", "kartenname": "Sol Ring"}}

    sauber = vor_dem_senden(ereignis)

    assert sauber["extra"]["passwort"] == "[entfernt]"
    assert sauber["extra"]["stripe_secret_key"] == "[entfernt]"
    assert sauber["extra"]["jwt_secret_key"] == "[entfernt]"
    assert sauber["extra"]["kartenname"] == "Sol Ring"


def test_auch_tief_verschachtelt():
    ereignis = {"a": {"b": {"c": [{"refresh_token": "geheim"}]}}}

    sauber = vor_dem_senden(ereignis)

    assert sauber["a"]["b"]["c"][0]["refresh_token"] == "[entfernt]"


def test_gross_und_kleinschreibung_egal():
    sauber = vor_dem_senden({"h": {"COOKIE": "sitzung=1", "Set-Cookie": "x"}})

    assert sauber["h"]["COOKIE"] == "[entfernt]"
    assert sauber["h"]["Set-Cookie"] == "[entfernt]"


def test_saeubern_sprengt_nichts_bei_seltsamen_daten():
    """Der Versand darf an einem ungewöhnlichen Ereignis nicht scheitern."""
    assert vor_dem_senden({}) == {}
    assert vor_dem_senden({"a": None})["a"] is None
    assert vor_dem_senden({"a": {1: "x"}})["a"][1] == "x"


def test_die_wichtigsten_geheimnisse_stehen_auf_der_liste():
    for feld in ("authorization", "passwort", "jwt_secret_key",
                 "stripe_secret_key", "stripe_webhook_secret", "gemini_api_key"):
        assert feld in GEHEIME_FELDER


# ----------------------------------------------------------------------
# Einrichten
# ----------------------------------------------------------------------
def test_ohne_dsn_passiert_nichts(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert einrichten() is False


def test_leerer_dsn_zaehlt_als_nicht_gesetzt(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "   ")
    assert einrichten() is False


def test_fehlendes_paket_verhindert_den_start_nicht(monkeypatch):
    """Ein Überwachungswerkzeug, das die App am Start hindert, wäre die
    schlechteste aller Möglichkeiten."""
    import builtins

    monkeypatch.setenv("SENTRY_DSN", "https://beispiel@sentry.invalid/1")
    echtes_import = builtins.__import__

    def ohne_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("nicht installiert")
        return echtes_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", ohne_sentry)
    assert einrichten() is False


def test_kaputter_dsn_verhindert_den_start_nicht(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "das ist kein DSN")
    # Kein Absturz, nur ein False.
    assert einrichten() is False


@pytest.mark.parametrize("umgebung", ["development", "production"])
def test_mit_gueltigem_dsn_wird_eingerichtet(monkeypatch, umgebung):
    sentry_sdk = pytest.importorskip("sentry_sdk")

    aufrufe = {}

    def falsches_init(**kwargs):
        aufrufe.update(kwargs)

    monkeypatch.setattr(sentry_sdk, "init", falsches_init)
    monkeypatch.setenv("SENTRY_DSN", "https://beispiel@o0.ingest.sentry.io/1")
    monkeypatch.setenv("GRANA_ENV", umgebung)

    assert einrichten() is True
    assert aufrufe["environment"] == umgebung
    # Keine personenbezogenen Daten und die Säuberung ist eingehängt.
    assert aufrufe["send_default_pii"] is False
    assert aufrufe["before_send"] is vor_dem_senden


# ----------------------------------------------------------------------
# Der Fall, der beim Prüfen durchgerutscht ist
# ----------------------------------------------------------------------
def test_lokale_variablen_in_der_aufrufliste_werden_gesaeubert():
    """Der Fehler, den erst ein echter Sentry-Bericht zeigte: Sentry legt
    lokale Variablen sieben Ebenen tief ab --

        event -> exception -> values[] -> stacktrace -> frames[] -> vars

    -- und die Tiefenbegrenzung endete bei sechs. Die flachen Tests darüber
    waren alle grün, während "hunter2" ungehindert an den Dienst gegangen
    wäre."""
    ereignis = {
        "exception": {"values": [{
            "type": "ValueError",
            "stacktrace": {"frames": [{
                "function": "anmelden",
                "vars": {"passwort": "hunter2", "jwt_secret_key": "geheim-123",
                         "kartenname": "Sol Ring"},
            }]},
        }]},
    }

    sauber = str(vor_dem_senden(ereignis))

    assert "hunter2" not in sauber
    assert "geheim-123" not in sauber
    assert "Sol Ring" in sauber, "Unverfängliches muss erhalten bleiben"


def test_echtes_sentry_ereignis_enthaelt_keine_geheimnisse():
    """Dieselbe Prüfung an einem Bericht, den die Bibliothek selbst baut --
    damit sie auch dann greift, wenn Sentry seine Struktur ändert."""
    import sys

    sentry_sdk = pytest.importorskip("sentry_sdk")
    from sentry_sdk.client import _get_options
    from sentry_sdk.utils import event_from_exception

    def loesende_funktion():
        passwort = "hunter2"                      # noqa: F841 -- Zweck des Tests
        authorization = "Bearer abc.def.ghi"      # noqa: F841
        kartenname = "Sol Ring"                   # noqa: F841
        raise ValueError("Testfehler")

    optionen = _get_options(dsn="https://beispiel@o0.ingest.sentry.io/1",
                            include_local_variables=True)
    try:
        loesende_funktion()
    except ValueError:
        ereignis, _ = event_from_exception(sys.exc_info(), client_options=optionen)

    def variablen(ev):
        werte = {}
        for eintrag in ev.get("exception", {}).get("values", []):
            for rahmen in eintrag.get("stacktrace", {}).get("frames", []):
                werte.update(rahmen.get("vars") or {})
        return werte

    vorher = variablen(ereignis)
    assert "hunter2" in str(vorher.get("passwort")), \
        "Vorbedingung: die Bibliothek nimmt lokale Variablen mit"

    nachher = variablen(vor_dem_senden(ereignis))
    assert nachher["passwort"] == "[entfernt]"
    assert nachher["authorization"] == "[entfernt]"
    assert "Sol Ring" in str(nachher["kartenname"]), "Unverfängliches bleibt"
    assert "Testfehler" in str(vor_dem_senden(ereignis))
