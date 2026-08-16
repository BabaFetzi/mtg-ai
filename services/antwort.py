"""services/antwort.py -- grosse Antworten verpacken, ohne alle anderen Nutzer
auszubremsen.

Das Problem
-----------
Gibt eine Route ein einfaches ``dict`` zurück, macht FastAPI zwei Durchläufe
über den gesamten Baum: erst ``jsonable_encoder``, dann ``json.dumps``. Beides
läuft im Faden der Ereignisschleife, und solange es läuft, kommt **keine**
andere Anfrage dran -- auch kein Login und kein ``/health``.

Bei einer Sammlung mit 15000 Karten (4,9 MB Antwort) gemessen:

===================================  ========
Schritt                              Zeit
===================================  ========
Datenbank                            165 ms
Kartendaten zuordnen                  45 ms
Alben zusammenbauen                   72 ms
FastAPI ``jsonable_encoder``         **295 ms**
``json.dumps``                       **113 ms**
===================================  ========

Die 408 ms Verpackung waren also mehr als alles andere zusammen -- und genau
der Grund, warum ein simpler ``/health``-Aufruf unter Last bis zu 467 ms
brauchte.

Die Lösung
----------
``json_antwort()`` erzeugt die fertigen Bytes selbst. Der Aufrufer ruft sie in
einem Arbeitsfaden auf (``asyncio.to_thread``), zusammen mit dem Zusammenbauen
der Daten. FastAPI erkennt eine fertige ``Response`` und rührt sie nicht mehr
an -- beide Durchläufe entfallen. Direkt gemessen: 69 ms statt 408 ms, und
diese 69 ms blockieren niemanden mehr.

Gleiches Ergebnis, nicht nur ein ähnliches
------------------------------------------
Die Bytes sind identisch mit dem, was FastAPI erzeugt hätte:

* ``ensure_ascii=False``, ``allow_nan=False``, ``separators=(",", ":")`` sind
  exakt die Einstellungen aus ``starlette.responses.JSONResponse.render``.
* ``default=jsonable_encoder`` fängt alles ab, was ``json`` nicht von sich aus
  kennt (``datetime``, ``Decimal``, ``UUID``, Pydantic-Modelle, ``set`` ...) --
  und zwar mit demselben Code, den FastAPI sonst benutzt hätte. Es ist also
  keine zweite, abweichende Umwandlung, sondern dieselbe -- nur wird sie jetzt
  ausschliesslich für die seltenen Sonderfälle aufgerufen statt für jeden
  einzelnen Wert.

Wann man das *nicht* braucht
----------------------------
Für kleine Antworten ist der Gewinn bedeutungslos, und ein einfaches ``dict``
ist besser lesbar. Sinnvoll ist ``json_antwort()`` dort, wo die Antwort mit der
Sammlungsgrösse des Nutzers wächst.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response


def json_bytes(daten: Any) -> bytes:
    """Serialisiert ``daten`` genau so, wie FastAPI es getan hätte."""
    return json.dumps(
        daten,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        default=jsonable_encoder,
    ).encode("utf-8")


def json_antwort(daten: Any, status: int = 200) -> Response:
    """Fertig verpackte JSON-Antwort. Gedacht für den Aufruf im Arbeitsfaden."""
    return Response(
        content=json_bytes(daten),
        status_code=status,
        media_type="application/json",
    )
