"""
tests/conftest.py – Gemeinsame Test-Vorbereitung

Isoliert den Karten-Cache für die gesamte Testsitzung.

Grund: Die Tests liefen zuvor gegen dieselbe Cache-Datei wie die laufende App
(scryfall_cache.db im Projektverzeichnis). Dadurch
1. beeinflussten sich Tests gegenseitig (ein Test schrieb ein Ergebnis, das ein
   späterer Test dann aus dem Cache statt aus dem Code bekam), und
2. landeten Test-Attrappen dauerhaft im echten Cache -- ein Testlauf konnte so
   einem späteren echten Nutzer eine erfundene Antwort ausliefern
   (z.B. der Roast "This deck is absolute garbage.").
"""

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolierter_cache():
    """Legt den Cache der Testsitzung in eine eigene, temporäre Datei."""
    from services import cache as cache_modul

    verzeichnis = tempfile.mkdtemp(prefix="grana-test-cache-")
    pfad = os.path.join(verzeichnis, "test_cache.db")

    # Redis absichtlich unerreichbar: Tests sollen deterministisch den
    # SQLite-Pfad nutzen und niemals einen echten Redis-Server verändern.
    testcache = cache_modul.HybridCache(
        db_path=pfad, redis_url="redis://127.0.0.1:1", ttl_seconds=86400
    )

    original = cache_modul.scryfall_cache
    cache_modul.scryfall_cache = testcache

    # Module, die das Singleton direkt importiert haben, mitziehen.
    import importlib
    betroffen = [
        "services.scryfall", "services.card_query_tool",
        "routers.ai", "routers.cards", "routers.decks",
    ]
    originale = {}
    for name in betroffen:
        try:
            modul = importlib.import_module(name)
        except Exception:
            continue
        if hasattr(modul, "scryfall_cache"):
            originale[name] = modul.scryfall_cache
            modul.scryfall_cache = testcache

    yield testcache

    cache_modul.scryfall_cache = original
    for name, wert in originale.items():
        importlib.import_module(name).scryfall_cache = wert
    testcache._reset_sqlite_conn()


@pytest.fixture(autouse=True)
def leerer_cache_pro_test(isolierter_cache):
    """Jeder Test startet mit leerem Cache -- keine Übertragung zwischen Tests."""
    isolierter_cache._mem.clear()
    try:
        conn = isolierter_cache._get_sqlite_conn()
        conn.execute("DELETE FROM scryfall_cache")
        conn.commit()
    except Exception:
        pass
    yield
