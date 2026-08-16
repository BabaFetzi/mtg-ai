"""Jeder Endpunkt, der die Sammlung liest, braucht eine Grenze.

routers/collection.py hatte KEINE einzige, während routers/decks.py sechs hat.
Das fiel niemandem auf, weil slowapi ohne default_limits nur dort greift, wo
ein Dekorator steht: ein fehlender Dekorator sieht aus wie "kein Problem".

Diese Tests prüfen deshalb nicht nur, dass eine Grenze wirkt, sondern dass
überhaupt eine gesetzt ist -- sonst rutscht der nächste neue Endpunkt genauso
durch.
"""

import re

import pytest
from fastapi.testclient import TestClient

from auth import create_access_token
from main import app
from services.limiter import limiter


def _kopf(name: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': name})}"}


def _routen_mit_grenze() -> dict:
    """Pfad -> Grenzen.

    slowapi merkt sich die Grenzen nicht am Endpunkt, sondern in einer eigenen
    Ablage, geschlüsselt nach "modul.funktionsname". Deshalb der Umweg über die
    registrierten Routen der Anwendung.
    """
    ablage = getattr(limiter, "_route_limits", {})
    gefunden = {}
    for route in _alle_routen(app):
        ziel = getattr(route, "endpoint", None)
        if ziel is None:
            continue
        schluessel = f"{ziel.__module__}.{ziel.__name__}"
        if schluessel in ablage:
            gefunden[getattr(route, "path", "")] = ablage[schluessel]
    return gefunden


def _alle_routen(anwendung):
    """Alle Routen, auch die in eingebundenen Routern.

    app.routes liefert in dieser FastAPI-Fassung Hüllen (_IncludedRouter), die
    den eigentlichen Router unter `original_router` tragen. Ohne diesen
    Abstieg fände der Test gar keine Route und wäre stillschweigend
    wirkungslos -- er würde grün, ohne irgendetwas zu prüfen.
    """
    offen = list(getattr(anwendung, "routes", []))
    gesehen = set()
    while offen:
        eintrag = offen.pop()
        if id(eintrag) in gesehen:
            continue
        gesehen.add(id(eintrag))

        innen = getattr(eintrag, "original_router", None)
        if innen is not None:
            offen.extend(getattr(innen, "routes", []))
            continue
        kinder = getattr(eintrag, "routes", None)
        if kinder:
            offen.extend(kinder)
            continue
        yield eintrag


# Alles, was die Sammlung eines Nutzers liest oder verändert. Ein Aufruf hier
# kann je nach Sammlungsgröße hunderte Millisekunden Rechenzeit kosten.
SAMMLUNGSPFADE = [
    "/api/sammlung/{benutzername}",
    "/api/sammlung/{benutzername}/uebersicht",
    "/api/sammlung/{benutzername}/top",
    "/api/sammlung/{benutzername}/alben",
    "/api/sammlung/{benutzername}/kartennamen",
    "/api/sammlung/{benutzername}/filter",
    "/api/sammlung/{benutzername}/editions",
    "/api/sammlung/{benutzername}/export-csv",
    "/api/sammlung/{benutzername}/refresh-prices",
    "/api/sammlung/hinzufuegen",
    "/api/sammlung/loeschen",
    "/api/sammlung/album_loeschen",
    "/api/sammlung/import-csv",
    "/api/sammlung/aus-deck",
]


@pytest.mark.parametrize("pfad", SAMMLUNGSPFADE)
def test_jeder_sammlungsendpunkt_hat_eine_grenze(pfad):
    mit_grenze = _routen_mit_grenze()

    assert pfad in mit_grenze, (
        f"{pfad} hat keine Drosselung. Ohne sie kann ein einzelner Nutzer die "
        f"Arbeitsfäden belegen und alle anderen ausbremsen.")


def test_die_teuren_endpunkte_sind_enger_gefasst():
    """Der Vollabruf und die Preisaktualisierung lesen die GESAMTE Sammlung.
    Sie dürfen nicht dieselbe Grenze haben wie ein einzelnes Kartenupdate."""
    mit_grenze = _routen_mit_grenze()

    def je_minute(pfad):
        roh = str(mit_grenze[pfad][0].limit)
        treffer = re.search(r"(\d+)", roh)
        return int(treffer.group(1))

    voll = je_minute("/api/sammlung/{benutzername}")
    preise = je_minute("/api/sammlung/{benutzername}/refresh-prices")
    einzeln = je_minute("/api/sammlung/hinzufuegen")

    assert voll <= 20, "Vollabruf zu grosszügig"
    assert preise <= 10, "Preisaktualisierung zu grosszügig"
    assert einzeln > voll, "Einzelne Karten anzulegen muss häufiger gehen"


def test_die_grenze_greift_wirklich():
    """Beweist, dass der Dekorator nicht nur dasteht.

    Der Vollabruf ist auf 10 je Minute gesetzt -- der elfte muss 429 liefern.
    """
    limiter.reset()
    kopf = _kopf("drossel_test")

    kodes = [client_get("/api/sammlung/drossel_test", kopf) for _ in range(12)]

    assert 429 in kodes, f"Keine Drosselung ausgelöst: {kodes}"
    # Und die ersten Aufrufe müssen durchgekommen sein -- eine Grenze, die
    # sofort sperrt, wäre genauso kaputt.
    assert kodes[0] != 429


def client_get(pfad: str, kopf: dict) -> int:
    with TestClient(app) as client:
        return client.get(pfad, headers=kopf).status_code


def test_verschiedene_nutzer_teilen_sich_kein_kontingent():
    """Gezählt wird je angemeldetem Nutzer. Zählte es je IP, teilten sich alle
    Nutzer hinter einem Reverse-Proxy ein einziges Kontingent -- genau der
    Fehler, der im Lasttest 44 Prozent aller Anfragen hat scheitern lassen.
    """
    limiter.reset()

    for _ in range(12):
        client_get("/api/sammlung/vielnutzer", _kopf("vielnutzer"))

    # Ein anderer Nutzer, dieselbe Adresse: muss unbehelligt sein.
    assert client_get("/api/sammlung/frischling", _kopf("frischling")) != 429
