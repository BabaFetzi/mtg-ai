"""tests/test_jwt_secret.py – Der Token-Schlüssel muss in Produktion erzwungen sein.

Hintergrund: Fehlte JWT_SECRET_KEY, erzeugte jeder Prozess einen eigenen
Zufallsschlüssel und gab nur eine Warnung aus. Folge im Betrieb: bei jedem
Neustart wurden alle Anmeldungen ungültig (die 401er im Log), und mit mehreren
Arbeitsprozessen schlug die Anmeldung sporadisch fehl, weil Worker A ein Token
nicht prüfen konnte, das Worker B ausgestellt hatte. Eine überlesbare Warnung
ist dagegen keine Absicherung -- in Produktion muss der Start scheitern.
"""

import importlib
import sys

import pytest


def _auth_neu_laden(monkeypatch, env: dict):
    for name in ("GRANA_ENV", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, wert in env.items():
        monkeypatch.setenv(name, wert)
    # load_dotenv() darf die .env nicht wieder hereinholen und den Test verfälschen.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
    sys.modules.pop("auth", None)
    return importlib.import_module("auth")


@pytest.fixture(autouse=True)
def _auth_wieder_herstellen():
    """Nach jedem Test das echte auth-Modul zurückholen -- andere Testdateien
    importieren es und würden sonst eine manipulierte Fassung sehen."""
    yield
    sys.modules.pop("auth", None)
    importlib.import_module("auth")


def test_produktion_ohne_schluessel_startet_nicht(monkeypatch):
    with pytest.raises(RuntimeError) as fehler:
        _auth_neu_laden(monkeypatch, {"GRANA_ENV": "production"})
    assert "JWT_SECRET_KEY" in str(fehler.value)


def test_produktion_mit_zu_kurzem_schluessel_startet_nicht(monkeypatch):
    with pytest.raises(RuntimeError) as fehler:
        _auth_neu_laden(monkeypatch, {"GRANA_ENV": "production", "JWT_SECRET_KEY": "kurz"})
    assert "zu kurz" in str(fehler.value)


def test_produktion_mit_gueltigem_schluessel_startet(monkeypatch):
    modul = _auth_neu_laden(monkeypatch, {
        "GRANA_ENV": "production",
        "JWT_SECRET_KEY": "a" * 64,
    })
    assert modul.SECRET_KEY == "a" * 64
    assert modul.IST_PRODUKTION is True


def test_entwicklung_ohne_schluessel_laeuft_weiter(monkeypatch):
    """Lokal soll niemand gezwungen sein, erst eine .env anzulegen."""
    modul = _auth_neu_laden(monkeypatch, {})
    assert len(modul.SECRET_KEY) >= modul.MIN_SECRET_LAENGE
    assert modul.IST_PRODUKTION is False


def test_leerzeichen_gelten_nicht_als_schluessel(monkeypatch):
    """JWT_SECRET_KEY="   " in der .env ist derselbe Fehler wie gar kein Wert."""
    with pytest.raises(RuntimeError):
        _auth_neu_laden(monkeypatch, {"GRANA_ENV": "production", "JWT_SECRET_KEY": "   "})
