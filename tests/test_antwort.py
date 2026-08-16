"""Die selbst verpackte JSON-Antwort muss dasselbe liefern wie FastAPI.

Der Grund für services/antwort.py ist Geschwindigkeit: FastAPIs eigener Weg
(jsonable_encoder + json.dumps) blockierte bei einer grossen Sammlung die
Ereignisschleife für über 400 ms und hielt damit alle anderen Nutzer an.

Eine schnellere Verpackung ist aber nur dann eine Verbesserung, wenn sie
BYTEGLEICH ist. Weicht sie irgendwo ab, ändert sich still und leise die API --
und das Frontend bekommt plötzlich andere Werte. Genau das prüfen diese Tests.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from services.antwort import json_antwort, json_bytes


def _wie_fastapi(daten):
    """Baut dieselbe Antwort über den normalen FastAPI-Weg und gibt die Bytes."""
    app = FastAPI()

    @app.get("/x")
    async def x():
        return daten

    with TestClient(app) as client:
        return client.get("/x").content


BEISPIELE = [
    pytest.param({"erfolg": True, "alben": {}}, id="leer"),
    pytest.param({"a": [1, 2.5, None, True, False]}, id="grundtypen"),
    pytest.param({"name": "Æther Vial – Grüße, 日本語"}, id="umlaute-und-unicode"),
    pytest.param({"preis": Decimal("12.34")}, id="decimal"),
    pytest.param({"stand": datetime(2024, 5, 1, 12, 30, 15)}, id="datetime"),
    pytest.param({"tag": date(2024, 5, 1)}, id="date"),
    pytest.param({"id": UUID("12345678-1234-5678-1234-567812345678")}, id="uuid"),
    pytest.param({"tupel": (1, "zwei", 3)}, id="tupel"),
    pytest.param({"verschachtelt": {"a": [{"b": {"c": [1, {"d": None}]}}]}}, id="tief"),
    pytest.param(
        {"erfolg": True, "alben": {
            "Ordner 1": [{"id": 7, "name": "Lightning Bolt", "bild_url": None,
                          "preis": "1.20", "livePreis": 1.2, "foil": False,
                          "sprache": None, "zustand": "NM", "edition": "lea",
                          "sammlernummer": "161", "edition_name": "Limited Edition Alpha"}]}},
        id="echte-sammlungsform"),
]


@pytest.mark.parametrize("daten", BEISPIELE)
def test_bytegleich_mit_fastapi(daten):
    assert json_bytes(daten) == _wie_fastapi(daten)


def test_antwort_hat_den_richtigen_inhaltstyp():
    antwort = json_antwort({"erfolg": True})

    assert antwort.status_code == 200
    assert antwort.media_type == "application/json"
    assert json.loads(antwort.body) == {"erfolg": True}


def test_route_mit_fertiger_antwort_wird_nicht_nochmal_verpackt():
    """FastAPI darf eine fertige Response nicht ein zweites Mal umwandeln --
    sonst käme ein JSON-String im JSON heraus."""
    app = FastAPI()

    @app.get("/x")
    async def x():
        return json_antwort({"erfolg": True, "karten": [{"id": 1}]})

    with TestClient(app) as client:
        antwort = client.get("/x")

    assert antwort.headers["content-type"].startswith("application/json")
    assert antwort.json() == {"erfolg": True, "karten": [{"id": 1}]}


def test_sammlungsrouten_verpacken_selbst():
    """Die Sammlungsrouten müssen eine fertige Response liefern.

    Schreibt jemand hier später wieder ``return {"erfolg": True, ...}``, sieht
    das harmloser aus und funktioniert auch -- aber FastAPI verpackt dann
    wieder selbst, in der Ereignisschleife, und die Blockade ist zurück. Kein
    Test würde das bemerken, denn die Antwort bleibt ja identisch. Deshalb
    dieser Test: er prüft die Bauweise, nicht das Ergebnis.
    """
    import inspect

    from routers.collection import _filter_antwort, _sammlung_antwort

    for bauer in (_sammlung_antwort, _filter_antwort):
        assert inspect.signature(bauer).return_annotation is Response, \
            f"{bauer.__name__} soll eine fertige Response bauen"

    zeilen = [{"id": 1, "karten_name": "Sol Ring", "album_name": "Ordner 1",
               "bild_url": "http://x/y.jpg", "preis": "1.50"}]
    daten = {1: {"name": "Sol Ring", "set": "c21", "set_name": "Commander 2021",
                 "image": "http://x/y.jpg", "cmc": 1.0, "rarity": "uncommon",
                 "type": "Artifact", "colors": []}}

    antwort = _sammlung_antwort(zeilen, daten)
    assert isinstance(antwort, Response)
    assert json.loads(antwort.body)["alben"]["Ordner 1"][0]["name"] == "Sol Ring"

    gefiltert = _filter_antwort(zeilen, daten, None, None, None, None, None, None, None,
                                1, 100, "name")
    assert isinstance(gefiltert, Response)
    assert json.loads(gefiltert.body)["karten"][0]["name"] == "Sol Ring"


def test_nan_wird_abgelehnt_wie_bei_fastapi():
    """NaN ist kein gültiges JSON. FastAPI lehnt es ab -- wir auch, statt
    stillschweigend 'NaN' auszuliefern, womit kein Browser etwas anfangen kann."""
    with pytest.raises(ValueError):
        json_bytes({"preis": float("nan")})
