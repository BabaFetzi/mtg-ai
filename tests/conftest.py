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
    # Jedes Modul, das `from services.cache import scryfall_cache` macht, hält
    # eine eigene Referenz auf das Singleton und muss hier stehen. Fehlt eines,
    # schreibt es im Test in die ECHTE Cache-Datei -- so fiel routers.payments
    # auf, als der Abo-Preis zwischengespeichert wurde.
    betroffen = betroffen_module()
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


@pytest.fixture(autouse=True)
def leeres_kartennamen_gedaechtnis():
    """Das dauerhafte Kartennamen-Gedächtnis darf Tests nicht überdauern.

    Dieselbe Überlegung wie beim Cache oben, nur schärfer: das Gedächtnis
    liegt in der ECHTEN Anwendungsdatenbank und hat ausdrücklich KEIN
    Verfallsdatum. Ohne diese Isolierung schrieben Tests dauerhaft in
    mtg_app.db -- und der nächste Test bekam die Antwort des vorherigen.

    Genau so ist es aufgefallen: ein Test erwartete "Fearsome Goblin Pair",
    bekam aber "Fearsome Goblin Duo" aus einem früheren Testfall.

    Ersetzt wird die Ablage, nicht die Logik -- so laufen die Prüfungen in
    services/kartennamen_gedaechtnis.py (bestätigte Namen, doppelte Einträge,
    leere Werte) im Test wirklich mit.

    Bewusst OHNE die monkeypatch-Fixture, obwohl die kürzer wäre: monkeypatch
    ist funktionsweit und wird beim ERSTEN Anfordern eingerichtet. Fordert eine
    autouse-Fixture sie an, wird sie früher eingerichtet und damit später
    abgeräumt -- nach den autouse-Fixtures einzelner Testdateien. In
    tests/test_jwt_secret.py lädt genau so eine Fixture beim Abräumen das
    auth-Modul neu und scheiterte dann daran, dass GRANA_ENV=production noch
    stand. Von Hand sichern und zurücksetzen hat diese Fernwirkung nicht.
    """
    from services import kartennamen_gedaechtnis as gedaechtnis

    ablage: dict = {}

    async def _nachschlagen(begriff):
        schluessel = gedaechtnis._schluessel(begriff)
        if schluessel in ablage:
            ablage[schluessel]["treffer"] += 1
            return ablage[schluessel]["name"]
        return None

    async def _merken(begriff, karten_name, quelle=gedaechtnis.QUELLE_KI):
        schluessel = gedaechtnis._schluessel(begriff)
        name = (karten_name or "").strip()
        if not schluessel or not name or schluessel == name.lower():
            return False
        if schluessel in ablage:
            return False
        ablage[schluessel] = {"name": name, "quelle": quelle, "treffer": 0}
        return True

    async def _vergessen(begriff):
        return ablage.pop(gedaechtnis._schluessel(begriff), None) is not None

    async def _stand():
        return {"eintraege": len(ablage),
                "ersparte_ki_anfragen": sum(e["treffer"] for e in ablage.values())}

    ersatz = {"nachschlagen": _nachschlagen, "merken": _merken,
              "vergessen": _vergessen, "stand": _stand}
    originale = {name: getattr(gedaechtnis, name) for name in ersatz}
    for name, funktion in ersatz.items():
        setattr(gedaechtnis, name, funktion)
    try:
        yield ablage
    finally:
        for name, funktion in originale.items():
            setattr(gedaechtnis, name, funktion)


def test_conftest_kennt_alle_module_mit_eigener_cache_referenz():
    """Wächter gegen eine veraltete Liste oben.

    Jedes Modul mit `from services.cache import scryfall_cache` hält eine
    eigene Referenz auf das Singleton. Fehlt es in `betroffen`, schreibt es im
    Test in die ECHTE Cache-Datei -- ein Testlauf kann dann einem späteren
    echten Nutzer eine erfundene Antwort ausliefern. Genau so fiel
    routers.payments auf.
    """
    import pathlib
    import re

    wurzel = pathlib.Path(__file__).resolve().parent.parent
    gefunden = set()
    for datei in list((wurzel / "routers").glob("*.py")) + list((wurzel / "services").glob("*.py")):
        text = datei.read_text(encoding="utf-8")
        if re.search(r"^from services\.cache import .*scryfall_cache", text, re.M):
            gefunden.add(f"{datei.parent.name}.{datei.stem}")

    fehlend = gefunden - set(betroffen_module())
    assert not fehlend, (
        "Diese Module halten eine eigene scryfall_cache-Referenz, stehen aber "
        f"nicht in der Liste in conftest.py: {sorted(fehlend)}"
    )


def betroffen_module():
    """Die Liste aus isolierter_cache -- hier einmal zentral, damit der Wächter
    oben sie prüfen kann."""
    return [
        "services.scryfall", "services.card_query_tool",
        "services.multilingual_search",
        "routers.ai", "routers.cards", "routers.collection",
        "routers.decks", "routers.payments",
    ]
