"""Leere Umgebungsvariablen duerfen den Standardwert nicht ueberschreiben.

Der Fall, der das ausgeloest hat: in der .env stand

    GEMINI_MODEL=

und danach scheiterte JEDER KI-Aufruf mit "model is required". Grund ist eine
Eigenheit von os.getenv, die man leicht uebersieht -- der Standardwert gilt nur,
wenn die Variable GAR NICHT existiert. Eine vorhandene, leere Variable liefert
"".

Das ist deshalb so gefaehrlich, weil .env.example jede Variable auflistet und
die meisten ohne Wert. Wer die Datei kopiert -- also jeder -- hat damit lauter
vorhandene Leerwerte.
"""

import logging

import pytest

from services import umgebung


# ----------------------------------------------------------------------
# Der eigentliche Punkt
# ----------------------------------------------------------------------

@pytest.mark.parametrize("wert", ["", "   ", "\t", "\n"])
def test_leer_zaehlt_wie_nicht_gesetzt(monkeypatch, wert):
    monkeypatch.setenv("GRANA_TEST_WERT", wert)

    assert umgebung.roh("GRANA_TEST_WERT") is None
    assert umgebung.text("GRANA_TEST_WERT", "standard") == "standard"
    assert umgebung.ganzzahl("GRANA_TEST_WERT", 42) == 42
    assert umgebung.zahl("GRANA_TEST_WERT", 1.5) == 1.5
    assert umgebung.schalter("GRANA_TEST_WERT", True) is True


def test_nicht_gesetzt_ergibt_den_standard(monkeypatch):
    monkeypatch.delenv("GRANA_TEST_WERT", raising=False)

    assert umgebung.text("GRANA_TEST_WERT", "standard") == "standard"
    assert umgebung.ganzzahl("GRANA_TEST_WERT", 42) == 42


def test_ein_echter_wert_gewinnt(monkeypatch):
    monkeypatch.setenv("GRANA_TEST_WERT", "  echt  ")

    assert umgebung.text("GRANA_TEST_WERT", "standard") == "echt"


# ----------------------------------------------------------------------
# Zahlen
# ----------------------------------------------------------------------

def test_zahlen_werden_gelesen(monkeypatch):
    monkeypatch.setenv("GRANA_TEST_WERT", "8080")
    assert umgebung.ganzzahl("GRANA_TEST_WERT", 587) == 8080

    monkeypatch.setenv("GRANA_TEST_WERT", "0.25")
    assert umgebung.zahl("GRANA_TEST_WERT", 1.0) == 0.25


def test_deutsches_komma_wird_akzeptiert(monkeypatch):
    """Wer eine Zahl von einer deutschen Seite abschreibt, tippt ein Komma."""
    monkeypatch.setenv("GRANA_TEST_WERT", "0,25")

    assert umgebung.zahl("GRANA_TEST_WERT", 1.0) == 0.25


def test_unlesbare_zahl_stuerzt_nicht_ab_sondern_meldet(monkeypatch, caplog):
    """Vorher war das ein ValueError beim IMPORT: ein Tippfehler in SMTP_PORT
    und die ganze Anwendung startete nicht mehr. Fuer eine Nebensaechlichkeit
    die komplette Seite abschalten waere die schlechtere Antwort."""
    monkeypatch.setenv("GRANA_TEST_WERT", "fuenfhundert")

    with caplog.at_level(logging.ERROR):
        assert umgebung.ganzzahl("GRANA_TEST_WERT", 587) == 587

    meldung = caplog.text
    assert "GRANA_TEST_WERT" in meldung      # welche Variable
    assert "fuenfhundert" in meldung          # welcher Wert
    assert "587" in meldung                   # was stattdessen gilt


# ----------------------------------------------------------------------
# Schalter
# ----------------------------------------------------------------------

@pytest.mark.parametrize("wert", ["1", "true", "TRUE", "yes", "on", "ja"])
def test_schalter_an(monkeypatch, wert):
    monkeypatch.setenv("GRANA_TEST_WERT", wert)
    assert umgebung.schalter("GRANA_TEST_WERT", False) is True


@pytest.mark.parametrize("wert", ["0", "false", "FALSE", "no", "off", "nein"])
def test_schalter_aus(monkeypatch, wert):
    monkeypatch.setenv("GRANA_TEST_WERT", wert)
    assert umgebung.schalter("GRANA_TEST_WERT", True) is False


def test_unbekannter_schalterwert_behaelt_den_standard(monkeypatch, caplog):
    """Ein unverstandener Wert darf keine Funktion abschalten -- weder still
    noch ueberhaupt."""
    monkeypatch.setenv("GRANA_TEST_WERT", "vielleicht")

    with caplog.at_level(logging.ERROR):
        assert umgebung.schalter("GRANA_TEST_WERT", True) is True

    assert "GRANA_TEST_WERT" in caplog.text


# ----------------------------------------------------------------------
# Jeder Aufruf liest neu
# ----------------------------------------------------------------------

def test_aenderung_wirkt_ohne_neustart(monkeypatch):
    monkeypatch.setenv("GRANA_TEST_WERT", "eins")
    assert umgebung.text("GRANA_TEST_WERT") == "eins"

    monkeypatch.setenv("GRANA_TEST_WERT", "zwei")
    assert umgebung.text("GRANA_TEST_WERT") == "zwei"


# ======================================================================
# Die echten Stellen -- eine kopierte .env.example
# ======================================================================
# .env.example listet jede Variable auf, die meisten ohne Wert. Wer die Datei
# kopiert, startet also mit lauter vorhandenen Leerwerten. Diese Tests laden
# die betroffenen Module genau so und pruefen, dass die Standardwerte greifen.
#
# Vor dieser Aenderung endete derselbe Ablauf dreimal toedlich, jedesmal schon
# beim Import:
#   DATABASE_URL=   -> create_async_engine("")  ArgumentError
#   SMTP_PORT=      -> int("")                  ValueError
#   LOG_LEVEL=      -> basicConfig(level="")    ValueError
# und einmal still falsch:
#   GEMINI_MODEL=   -> jeder KI-Aufruf "model is required"

import importlib

# Alle Variablen, die in .env.example ohne Wert stehen und irgendwo einen
# Standard haben.
LEER_WIE_IN_DER_BEISPIELDATEI = [
    "GEMINI_MODEL", "GEMINI_MODEL_LITE", "GEMINI_MODEL_FALLBACK",
    "GEMINI_MODEL_LITE_FALLBACK", "DATABASE_URL", "SQLITE_PATH", "REDIS_URL",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_FROM", "SMTP_TLS_MODE",
    "LOG_LEVEL", "GRANA_ENV", "PREMIUM_CURRENCY", "PREMIUM_INTERVAL",
    "FRONTEND_URL", "PASSWORT_RESET_MINUTEN", "SENTRY_TRACES_SAMPLE_RATE",
    "GRANA_VERSION", "UVICORN_WORKERS", "ALLOWED_ORIGINS",
]


@pytest.fixture
def kopierte_beispieldatei(monkeypatch):
    """Jede Variable vorhanden, aber leer -- wie nach `cp .env.example .env`."""
    for name in LEER_WIE_IN_DER_BEISPIELDATEI:
        monkeypatch.setenv(name, "")
    # load_dotenv() darf die echte .env nicht wieder hereinholen.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)


def test_leeres_gemini_model_ergibt_den_alias(kopierte_beispieldatei):
    """Der gemeldete Fehler: "model is required." bei jedem einzelnen Aufruf.

    Ein leerer Modellname ging an Google, noch bevor ueberhaupt eine Anfrage
    hinausging -- deshalb war auch die Modellspalte im Protokoll leer.
    """
    from services import ai_service
    ai_service = importlib.reload(ai_service)

    assert ai_service.MODEL_NAME == "gemini-flash-latest"
    assert ai_service.MODEL_LITE_NAME == "gemini-flash-lite-latest"
    # Die Ersatzmodelle haengen an den beiden -- auch sie duerfen nicht leer sein.
    assert ai_service.MODEL_FALLBACK_NAME
    assert ai_service.MODEL_LITE_FALLBACK_NAME


def test_leeres_database_url_ergibt_die_lokale_sqlite(kopierte_beispieldatei):
    """.env.example sagt ausdruecklich "leer lassen fuer lokale SQLite" --
    und genau das liess die Anwendung vorher gar nicht erst starten."""
    import database
    database = importlib.reload(database)

    assert database.DATABASE_URL == "sqlite+aiosqlite:///mtg_app.db"
    assert database.engine is not None


def test_leerer_smtp_port_bleibt_587(kopierte_beispieldatei):
    from services import mailer
    mailer = importlib.reload(mailer)

    assert mailer.SMTP_PORT == 587
    assert mailer.SMTP_TLS_MODUS == "starttls"
    # Ohne Host ist der Versand nicht eingerichtet -- das soll so bleiben.
    assert mailer.mailversand_konfiguriert() is False


def test_leeres_grana_env_heisst_entwicklung_nicht_produktion(kopierte_beispieldatei):
    """Wichtig fuer die Pflichtpruefung von JWT_SECRET_KEY: der Wert muss
    eindeutig sein, nicht ein leerer Text, der zufaellig nicht "production"
    ist."""
    import auth
    auth = importlib.reload(auth)

    assert auth.GRANA_ENV == "development"
    assert auth.IST_PRODUKTION is False


def test_produktion_wird_weiterhin_erkannt(monkeypatch):
    """Die Gegenprobe -- der Standard darf einen echten Wert nicht verdecken."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
    monkeypatch.setenv("GRANA_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)

    import auth
    auth = importlib.reload(auth)

    assert auth.IST_PRODUKTION is True
