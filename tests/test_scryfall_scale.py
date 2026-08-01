"""
tests/test_scryfall_scale.py – Lastfestigkeit des Scryfall-Zugriffs

Beweist die Korrekturen, die den Rate-Limit-Sturm (429-Kaskade) verursacht
haben und die App bei vielen gleichzeitigen Nutzern tragfähig machen:

1. Ein gedrosselter Batch löst KEINE Einzel-Fallback-Kaskade aus.
2. Parallele Anfragen zur selben Karte teilen sich EINEN Netzwerkabruf.
3. Veraltete Cache-Einträge werden sofort ausgeliefert (nie blockierend).
4. Die globale Drossel begrenzt gleichzeitige Anfragen prozessweit.
5. Fehlende Preise werden negativ gecacht (kein Dauer-Nachschlagen).
"""

import asyncio
from unittest.mock import patch

import httpx
import pytest

import services.scryfall as sf


# ----------------------------------------------------------------------
# Test-Doubles
# ----------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    """Minimaler httpx-AsyncClient-Ersatz, der jeden Aufruf protokolliert."""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        result = self._handler(method, url, kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeCache:
    def __init__(self, initial=None):
        self.data = dict(initial or {})

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


def _card(name, with_oracle=True):
    d = {
        "name": name,
        "type_line": "Artifact",
        "cmc": 1.0,
        "colors": [],
        "color_identity": [],
        "prices": {"eur": "1.00"},
        "legalities": {},
        "image_uris": {"normal": f"img/{name}"},
    }
    if with_oracle:
        d["oracle_text"] = f"{name} rules text"
    return d


@pytest.fixture(autouse=True)
def _reset_globals():
    """Limiter-Cooldown und Single-Flight-Registry zwischen Tests zurücksetzen."""
    sf._limiter._cooldown_until = 0.0
    sf._limiter._next_slot = 0.0
    sf._inflight.clear()
    sf._refresh_queued.clear()
    yield
    sf._limiter._cooldown_until = 0.0
    sf._limiter._next_slot = 0.0
    sf._inflight.clear()
    sf._refresh_queued.clear()


# ----------------------------------------------------------------------
# 1. Kernfix: 429 darf keine Einzel-Fallback-Kaskade auslösen
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limited_batch_does_not_cascade_into_single_lookups():
    """DER Bug hinter dem Log-Sturm: Nach einem 429 auf den Sammel-Abruf galten
    alle 75 Karten als 'nicht gefunden' und lösten je zwei Einzelanfragen aus
    (Fuzzy + Sprachsuche) -- Drosselung erzeugte so MEHR Last."""
    names = [f"Karte {i}" for i in range(75)]

    def handler(method, url, kwargs):
        return FakeResponse(429, headers={"Retry-After": "1"})

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", FakeCache()):
        result = await sf.fetch_card_details_cached(names)

    assert result == {}
    # Nur die Batch-Versuche (1 Versuch + 1 Wiederholung), KEINE Einzelabrufe.
    assert len(client.calls) <= 2, f"Kaskade! {len(client.calls)} Aufrufe statt <=2"
    assert all("cards/collection" in url for _, url in client.calls)
    assert not any("named?fuzzy" in url or "cards/search" in url for _, url in client.calls)


@pytest.mark.asyncio
async def test_successful_batch_still_falls_back_for_unknown_names():
    """Gegenprobe: Bei einer ERFOLGREICHEN Batch-Antwort muss der Fallback für
    tatsächlich unbekannte Namen weiterhin greifen."""
    def handler(method, url, kwargs):
        if "cards/collection" in url:
            return FakeResponse(200, {"data": [_card("Sol Ring")]})
        if "named?fuzzy" in url:
            return FakeResponse(200, _card("Lightning Bolt"))
        return FakeResponse(404)

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", FakeCache()):
        result = await sf.fetch_card_details_cached(["Sol Ring", "Lightnin Bolt"])

    assert "sol ring" in result
    assert "lightnin bolt" in result  # per Fuzzy-Fallback aufgelöst
    assert any("named?fuzzy" in url for _, url in client.calls)


# ----------------------------------------------------------------------
# 2. Thundering Herd: gleiche Karte parallel = ein Netzwerkabruf
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_requests_for_same_card_share_one_fetch():
    """1000 Nutzer, dieselbe noch nicht gecachte Karte -> EIN Scryfall-Abruf."""
    batch_calls = 0
    gate = asyncio.Event()

    async def handler(method, url, kwargs):
        nonlocal batch_calls
        if "cards/collection" in url:
            batch_calls += 1
            await gate.wait()  # ersten Abruf offen halten
            return FakeResponse(200, {"data": [_card("Sol Ring")]})
        return FakeResponse(404)

    client = FakeClient(handler)
    cache = FakeCache()
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", cache):
        tasks = [
            asyncio.create_task(sf.fetch_card_details_cached(["Sol Ring"]))
            for _ in range(20)
        ]
        await asyncio.sleep(0.05)  # alle laufen in denselben In-Flight-Eintrag
        gate.set()
        results = await asyncio.gather(*tasks)

    assert batch_calls == 1, f"{batch_calls} Abrufe statt 1 (Thundering Herd)"
    assert all(r.get("sol ring", {}).get("name") == "Sol Ring" for r in results)


@pytest.mark.asyncio
async def test_inflight_registry_is_cleared_on_error():
    """Auch wenn der Abruf scheitert, dürfen keine hängenden In-Flight-Einträge
    zurückbleiben (sonst warten Folgeanfragen ins Timeout)."""
    def handler(method, url, kwargs):
        raise RuntimeError("Netzwerk weg")

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", FakeCache()):
        await sf.fetch_card_details_cached(["Sol Ring"])

    assert sf._inflight == {}


# ----------------------------------------------------------------------
# 3. Stale-while-revalidate: alte Einträge blockieren nie
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_cache_entry_is_served_without_blocking():
    """Ein Cache-Eintrag ohne oracle_text (Alt-Format) wird SOFORT ausgeliefert.
    Vorher wurde er verworfen -> Massen-Refetch beim ersten Seitenaufruf."""
    stale = _card("Sol Ring", with_oracle=False)
    cache = FakeCache({"card:sol ring": stale})

    def handler(method, url, kwargs):
        return FakeResponse(200, {"data": [_card("Sol Ring")]})

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", cache):
        result = await sf.fetch_card_details_cached(["Sol Ring"])
        # Antwort kommt aus dem Cache -- ohne auf Netzwerk zu warten
        assert result["sol ring"]["name"] == "Sol Ring"
        assert client.calls == []
        # Hintergrund-Refresh darf laufen, aber erst NACH der Antwort
        await asyncio.sleep(0.05)

    assert any("cards/collection" in url for _, url in client.calls)


@pytest.mark.asyncio
async def test_background_refresh_is_capped():
    """Der Hintergrund-Refresh ist gedeckelt -- eine entwertete Cache-Generation
    darf nicht tausende Anfragen auf einmal auslösen."""
    names = [f"Karte {i}" for i in range(500)]
    cache = FakeCache({f"card:{n.lower()}": _card(n, with_oracle=False) for n in names})
    seen = []

    def handler(method, url, kwargs):
        seen.append(kwargs.get("json", {}).get("identifiers", []))
        return FakeResponse(200, {"data": []})

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", cache):
        result = await sf.fetch_card_details_cached(names)
        assert len(result) == 500  # alles sofort aus dem Cache
        await asyncio.sleep(0.05)

    refreshed = sum(len(ids) for ids in seen)
    assert refreshed <= sf.MAX_BACKGROUND_REFRESH, f"{refreshed} Karten auf einmal"


# ----------------------------------------------------------------------
# 4. Globale Drossel
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_limiter_caps_global_concurrency():
    """Die Drossel begrenzt gleichzeitige Scryfall-Anfragen prozessweit --
    unabhängig davon, wie viele Nutzer parallel Anfragen stellen."""
    current = 0
    peak = 0

    async def worker():
        nonlocal current, peak
        async with sf._limiter:
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.01)
            current -= 1

    await asyncio.gather(*[worker() for _ in range(30)])
    assert peak <= sf.SCRYFALL_MAX_CONCURRENCY


@pytest.mark.asyncio
async def test_limiter_cooldown_blocks_further_requests():
    """Nach einem 429 gilt der Cooldown für ALLE Aufrufer (under_pressure)."""
    assert sf._limiter.under_pressure is False
    sf._limiter.note_rate_limited(2.0)
    assert sf._limiter.under_pressure is True


# ----------------------------------------------------------------------
# 5. Preis-Lookup: negatives Caching
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_price_is_negatively_cached():
    """Karten ohne EUR-Preis (Promos) dürfen nicht bei jedem Aufruf erneut
    nachgeschlagen werden -- das war der Verstärker des Anfragen-Sturms."""
    lookups = 0

    def handler(method, url, kwargs):
        nonlocal lookups
        lookups += 1
        return FakeResponse(200, {"data": [{"prices": {"eur": None}}]})

    client = FakeClient(handler)
    cache = FakeCache()
    with patch.object(sf, "scryfall_cache", cache):
        first = await sf._fetch_cheapest_paper_eur(client, "Promo Card")
        second = await sf._fetch_cheapest_paper_eur(client, "Promo Card")

    assert first is None and second is None
    assert lookups == 1, "zweiter Aufruf hätte aus dem Cache kommen müssen"


@pytest.mark.asyncio
async def test_price_lookup_skipped_while_rate_limited():
    """Unter Drosselung wird der (optionale) Preis-Lookup übersprungen, statt
    die Seite hängen zu lassen."""
    def handler(method, url, kwargs):
        raise AssertionError("darf unter Drosselung nicht aufgerufen werden")

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_cache", FakeCache()):
        sf._limiter.note_rate_limited(5.0)
        assert await sf._fetch_cheapest_paper_eur(client, "Irgendeine Karte") is None


# ----------------------------------------------------------------------
# 6. Begrenzte Degradation bei Ausfall des Sammel-Endpunkts
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_batch_outage_degrades_but_stays_bounded():
    """Fällt der Sammel-Endpunkt aus (5xx), bekommen Nutzer wenigstens einen
    TEIL der Daten -- aber die Einzelabfragen sind hart gedeckelt, damit ein
    Ausfall nicht wieder in eine Anfragen-Lawine umschlägt."""
    names = [f"Karte {i}" for i in range(75)]
    fuzzy_calls = 0

    def handler(method, url, kwargs):
        nonlocal fuzzy_calls
        if "cards/collection" in url:
            return FakeResponse(503)
        if "named?fuzzy" in url:
            fuzzy_calls += 1
            return FakeResponse(200, _card("Sol Ring"))
        return FakeResponse(404)

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", FakeCache()):
        result = await sf.fetch_card_details_cached(names)

    assert fuzzy_calls > 0, "Totalausfall statt Teil-Daten"
    assert fuzzy_calls <= sf.MAX_FALLBACK_LOOKUPS, f"{fuzzy_calls} Einzelabrufe (Lawine!)"
    assert len(result) > 0


@pytest.mark.asyncio
async def test_network_error_is_retried_once_not_fanned_out():
    """Ein Netzwerkaussetzer wird EINMAL wiederholt -- nicht durch viele
    Einzelanfragen kompensiert."""
    attempts = 0

    def handler(method, url, kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout")

    client = FakeClient(handler)
    with patch.object(sf, "scryfall_client", lambda **kw: client), \
         patch.object(sf, "scryfall_cache", FakeCache()):
        result = await sf.fetch_card_details_cached(["Sol Ring"])

    assert result == {}
    # 2 Batch-Versuche + max. 2 Fallback-Versuche (fuzzy/multilang) fuer die 1 Karte
    assert attempts <= 6, f"{attempts} Versuche -- keine Begrenzung"


def test_extract_card_info_includes_rarity_and_set():
    """Regression (T-2.4): Der Sammlungs-Filter braucht rarity + set. Fehlten sie
    im card_info, filterten Seltenheit und Edition immer auf 0 Treffer."""
    card_data = {
        "name": "Sol Ring",
        "type_line": "Artifact",
        "cmc": 1.0,
        "colors": [],
        "color_identity": [],
        "rarity": "uncommon",
        "set": "c21",
        "set_name": "Commander 2021",
        "prices": {"eur": "1.50"},
    }
    info = sf._extract_card_info(card_data)
    assert info["rarity"] == "uncommon"
    assert info["set"] == "c21"
    assert info["set_name"] == "Commander 2021"
