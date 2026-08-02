"""
tests/test_cache_performance.py – Batch-Lookup & Speicher-Cache

Sichert die Performance-Korrekturen ab, die die langen Ladezeiten in der
Sammlung verursacht haben:

1. get_many() liefert dieselben Werte wie Einzelabfragen -- aber in EINEM Zugriff.
2. Der prozessinterne Speicher-Cache liefert Treffer ohne Datei-Zugriff.
3. Abgelaufene Einträge werden auch im Batch-Pfad nicht ausgeliefert.
4. fetch_card_details_cached nutzt den Batch-Pfad, funktioniert aber weiterhin
   mit Caches ohne get_many().
"""

import os
import tempfile

import pytest

from services.cache import HybridCache


@pytest.fixture
def cache():
    path = tempfile.mktemp(suffix=".db")
    # Ohne erreichbares Redis -> SQLite-Pfad, genau der kritische Fall.
    instance = HybridCache(db_path=path, redis_url="redis://127.0.0.1:1", ttl_seconds=3600)
    yield instance
    instance._reset_sqlite_conn()
    if os.path.exists(path):
        os.remove(path)


def test_get_many_matches_single_gets(cache):
    for i in range(50):
        cache.set(f"card:k{i}", {"name": f"Karte {i}"})

    cache._mem.clear()
    einzeln = {k: cache.get(k) for k in (f"card:k{i}" for i in range(50))}
    cache._mem.clear()
    gebuendelt = cache.get_many([f"card:k{i}" for i in range(50)])

    assert gebuendelt == einzeln
    assert len(gebuendelt) == 50


def test_get_many_omits_unknown_keys(cache):
    cache.set("card:bekannt", {"name": "Bekannt"})
    cache._mem.clear()

    treffer = cache.get_many(["card:bekannt", "card:gibtesnicht"])

    assert "card:bekannt" in treffer
    assert "card:gibtesnicht" not in treffer


def test_memory_layer_serves_without_file_access(cache):
    cache.set("card:sol ring", {"name": "Sol Ring"})
    # Datei unbrauchbar machen: ein Treffer muss trotzdem aus dem Speicher kommen.
    cache._reset_sqlite_conn()
    cache.db_path = "/nicht/vorhanden/cache.db"

    assert cache.get("card:sol ring") == {"name": "Sol Ring"}
    assert cache.get_many(["card:sol ring"]) == {"card:sol ring": {"name": "Sol Ring"}}


def test_expired_entries_are_not_served_by_get_many(cache):
    cache.set("card:alt", {"name": "Alt"})
    # TTL auf 0 setzen und Speicher leeren -> Eintrag gilt als abgelaufen.
    cache.ttl = 0
    cache._mem.clear()

    assert cache.get_many(["card:alt"]) == {}


def test_memory_cache_is_bounded(cache):
    from services.cache import MEM_CACHE_MAX_ENTRIES

    for i in range(MEM_CACHE_MAX_ENTRIES + 100):
        cache._mem_set(f"card:x{i}", {"i": i})

    assert len(cache._mem) <= MEM_CACHE_MAX_ENTRIES


@pytest.mark.asyncio
async def test_fetch_uses_batch_lookup_when_available():
    """Der heiße Pfad darf pro Sammlung nur EINEN Cache-Zugriff machen."""
    import services.scryfall as sf

    class ZaehlenderCache:
        def __init__(self):
            self.batch_aufrufe = 0
            self.einzel_aufrufe = 0
            self.daten = {
                f"card:karte {i}": {"name": f"Karte {i}", "_cached_at": 9e18}
                for i in range(30)
            }

        def get_many(self, keys):
            self.batch_aufrufe += 1
            return {k: self.daten[k] for k in keys if k in self.daten}

        def get(self, key):
            self.einzel_aufrufe += 1
            return self.daten.get(key)

        def set(self, key, value):
            self.daten[key] = value

    fake = ZaehlenderCache()
    namen = [f"Karte {i}" for i in range(30)]

    from unittest.mock import patch
    with patch.object(sf, "scryfall_cache", fake):
        ergebnis = await sf.fetch_card_details_cached(namen)

    assert len(ergebnis) == 30
    assert fake.batch_aufrufe == 1, "Es darf nur EIN Batch-Lookup passieren"
    assert fake.einzel_aufrufe == 0, "Keine Einzelabfragen im heißen Pfad"


@pytest.mark.asyncio
async def test_fetch_still_works_with_cache_without_get_many():
    """Rückwärtskompatibel: Caches ohne get_many() müssen weiter funktionieren."""
    import services.scryfall as sf
    from unittest.mock import patch

    class EinfacherCache:
        def __init__(self):
            self.daten = {"card:sol ring": {"name": "Sol Ring", "_cached_at": 9e18}}

        def get(self, key):
            return self.daten.get(key)

        def set(self, key, value):
            self.daten[key] = value

    with patch.object(sf, "scryfall_cache", EinfacherCache()):
        ergebnis = await sf.fetch_card_details_cached(["Sol Ring"])

    assert ergebnis["sol ring"]["name"] == "Sol Ring"
