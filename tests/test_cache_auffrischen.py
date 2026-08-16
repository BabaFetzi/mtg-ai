"""tests/test_cache_auffrischen.py -- Wartungslauf für veraltete Karteneinträge.

Kommt ein Feld in den Kartendaten dazu (zuletzt `produced_mana`), sind alle
vorhandenen Cache-Einträge unvollständig. Im Betrieb heilt sich das langsam von
selbst; das Werkzeug macht daraus einen bewussten Durchlauf.

Der Fallstrick, in den ich beim Bauen selbst getappt bin: über
fetch_card_details_cached passiert NICHTS, weil die veralteten Einträge im Cache
gefunden, ausgeliefert und nur im Hintergrund nachgezogen werden -- was ein
kurzlebiger Wartungsprozess nie erlebt. Deshalb prüft ein Test genau das.
"""

import json
import sqlite3

import pytest

from werkzeuge import cache_auffrischen

FRISCH = {"name": "Sol Ring", "oracle_text": "{T}: Add {C}{C}.", "produced_mana": ["C"]}
ALT_OHNE_MANA = {"name": "Mountain", "oracle_text": "{T}: Add {R}."}
ALT_OHNE_TEXT = {"name": "Island"}


@pytest.fixture
def cache(tmp_path):
    pfad = tmp_path / "test_cache.db"
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE scryfall_cache (key TEXT PRIMARY KEY, value TEXT, timestamp REAL)")
    for eintrag in (FRISCH, ALT_OHNE_MANA, ALT_OHNE_TEXT):
        conn.execute(
            "INSERT INTO scryfall_cache VALUES (?, ?, 0)",
            (f"card:{eintrag['name'].lower()}", json.dumps(eintrag)),
        )
    # Ein Eintrag, der keine Karte ist -- darf nicht mitgezählt werden.
    conn.execute("INSERT INTO scryfall_cache VALUES ('preis:xyz', '{}', 0)")
    conn.commit()
    conn.close()
    return str(pfad)


def test_findet_nur_veraltete_karten(cache):
    namen, gesamt = cache_auffrischen.veraltete_namen(cache)

    assert gesamt == 3, "Nicht-Karten-Einträge zählen nicht mit"
    assert sorted(namen) == ["Island", "Mountain"]
    assert "Sol Ring" not in namen


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    assert cache_auffrischen.veraltete_namen(str(tmp_path / "gibtsnicht.db")) == ([], 0)


def test_kaputter_eintrag_wird_uebersprungen(cache):
    conn = sqlite3.connect(cache)
    conn.execute("INSERT INTO scryfall_cache VALUES ('card:kaputt', 'kein json', 0)")
    conn.commit()
    conn.close()

    namen, _ = cache_auffrischen.veraltete_namen(cache)
    assert "kaputt" not in namen


@pytest.mark.asyncio
async def test_laedt_wirklich_nach_statt_nur_aus_dem_cache_zu_lesen(monkeypatch):
    """Der Fallstrick: über den normalen Leseweg passiert gar nichts, weil die
    veralteten Einträge im Cache liegen und nur im Hintergrund nachgezogen
    werden. Der Wartungslauf muss den Netzweg nehmen."""
    geladen = []

    async def falsches_laden(namen):
        geladen.extend(namen)
        return {}

    monkeypatch.setattr(cache_auffrischen, "_fetch_uncached", falsches_laden)
    erledigt = await cache_auffrischen.auffrischen(["Mountain", "Island"], grenze=0)

    assert erledigt == 2
    assert geladen == ["Mountain", "Island"]


@pytest.mark.asyncio
async def test_grenze_wird_eingehalten(monkeypatch):
    geladen = []

    async def falsches_laden(namen):
        geladen.extend(namen)
        return {}

    monkeypatch.setattr(cache_auffrischen, "_fetch_uncached", falsches_laden)
    erledigt = await cache_auffrischen.auffrischen(["A", "B", "C", "D"], grenze=2)

    assert erledigt == 2
    assert geladen == ["A", "B"]


@pytest.mark.asyncio
async def test_ein_fehlgeschlagenes_buendel_stoppt_den_lauf_nicht(monkeypatch):
    """Ein Netzwerkfehler mitten im Durchlauf darf nicht alles Weitere
    verhindern -- sonst muss man von vorne anfangen."""
    monkeypatch.setattr(cache_auffrischen, "BUENDEL", 2)
    versuche = []

    async def manchmal_kaputt(namen):
        versuche.append(list(namen))
        if len(versuche) == 1:
            raise TimeoutError("Netz weg")
        return {}

    monkeypatch.setattr(cache_auffrischen, "_fetch_uncached", manchmal_kaputt)
    erledigt = await cache_auffrischen.auffrischen(["A", "B", "C", "D"], grenze=0)

    assert len(versuche) == 2
    assert erledigt == 2, "das zweite Bündel wurde trotz Fehler bearbeitet"
