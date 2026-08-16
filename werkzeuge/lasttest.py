#!/usr/bin/env python3
"""werkzeuge/lasttest.py -- hält die Seite viele gleichzeitige Nutzer aus?

Wozu
----
"Es fühlt sich schnell an" ist keine Aussage über tausend gleichzeitige Nutzer.
Dieses Werkzeug erzeugt echte Last gegen einen laufenden Server und misst, was
dabei herauskommt: Antwortzeiten (Mittelwert, 50/95/99 Prozent), Durchsatz und
vor allem Fehler. Ein Ausfall unter Last zeigt sich zuerst als Fehlerquote,
nicht als Langsamkeit.

Wichtig für die Aussagekraft
----------------------------
Der Lauf wärmt den Kartencache vor. Ohne das misst man die Antwortzeit von
Scryfall und deren Drosselung, nicht die eigene Anwendung -- und quält nebenbei
einen fremden Dienst.

Aufruf
------
    python -m werkzeuge.lasttest --server http://localhost:8000
    python -m werkzeuge.lasttest --nutzer 50 --runden 20
    python -m werkzeuge.lasttest --sammlung 1000   # grosse Sammlung anlegen

Der Lauf legt Testkonten an (Präfix "last-"). Gegen die echte Datenbank sollte
er deshalb nicht laufen -- dafür gibt es DATABASE_URL.

Was der erste Lauf zutage gefördert hat
---------------------------------------
Zwei echte Fehler, die ohne Last nicht sichtbar waren:

1. **44 Prozent HTTP 429.** Die Drosselung zählte nach IP-Adresse. Hinter
   einem Reverse-Proxy haben aber alle Nutzer dieselbe -- sie teilten sich
   also gemeinsam ein Kontingent und sperrten sich gegenseitig aus. Jetzt
   wird nach angemeldetem Nutzer gezählt (services/limiter.py).

2. **Ein Nutzer hielt alle anderen an.** Während eine Sammlung mit 15000
   Karten geladen wurde, brauchte ein simpler ``/health``-Aufruf bis zu
   472 ms. Ursache war nicht die Datenbank, sondern das Verpacken der
   Antwort im Faden der Ereignisschleife -- allein FastAPIs
   ``jsonable_encoder`` 295 ms. Behoben in services/antwort.py; gleicher
   Messaufbau danach: 117 ms.

3. **Die Seite lud, was sie gar nicht anzeigte.** Die Ordneruebersicht holte
   die vollstaendige Sammlung, um im Browser Summen zu bilden; die
   Kartensuche holte sie, um daraus eine Liste von Ordnernamen zu gewinnen;
   das Finanz-Dashboard holte sie, um zehn Karten anzuzeigen. Jede dieser
   Ansichten laedt jetzt nur noch ihr Ergebnis (/uebersicht, /alben, /top),
   und ein Ordner kommt seitenweise. Bei 15000 Karten: 25 KB statt 4,5 MB.

Wo die Grenzen liegen
---------------------
Auf 4 Kernen mit 2 Workern: rund 290 Anfragen/s, keine Fehler. Die Zahl je
Worker steht in .env.example.

Der Ausreisser bleibt die sehr grosse Sammlung: /uebersicht muss jede Zeile
anfassen, weil der Live-Preis nicht in der Datenbank steht. Das kostet bei
15000 Karten rund 130 ms -- im Arbeitsfaden, also ohne andere aufzuhalten.
Die Antwort waechst dabei nicht mehr mit der Sammlung, sondern nur noch mit
der Zahl der Ordner. Gemessen: 1000 Karten 13 ms/12 KB, 5000 Karten
44 ms/25 KB, 15000 Karten 128 ms/25 KB.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

# Karten, mit denen gearbeitet wird. Bewusst wenige und immer dieselben: nach
# dem Aufwärmen liegen sie im Cache, und gemessen wird die eigene Anwendung.
TESTKARTEN = [
    "Lightning Bolt", "Sol Ring", "Counterspell", "Llanowar Elves",
    "Swords to Plowshares", "Dark Ritual", "Birds of Paradise", "Brainstorm",
]

TESTDECK = ("4 Lightning Bolt\n4 Counterspell\n4 Brainstorm\n"
            "24 Mountain\n24 Island")


@dataclass
class Messung:
    name: str
    zeiten: List[float] = field(default_factory=list)
    fehler: Dict[str, int] = field(default_factory=dict)

    def erfolg(self, dauer: float) -> None:
        self.zeiten.append(dauer)

    def fehlschlag(self, grund: str) -> None:
        self.fehler[grund] = self.fehler.get(grund, 0) + 1

    @property
    def anzahl(self) -> int:
        return len(self.zeiten) + sum(self.fehler.values())

    @property
    def fehlerquote(self) -> float:
        return sum(self.fehler.values()) / self.anzahl if self.anzahl else 0.0

    def perzentil(self, anteil: float) -> float:
        if not self.zeiten:
            return 0.0
        sortiert = sorted(self.zeiten)
        rang = min(int(anteil * len(sortiert)), len(sortiert) - 1)
        return sortiert[rang]

    def zeile(self) -> str:
        if not self.anzahl:
            return f"  {self.name:26} -- keine Aufrufe"
        mittel = statistics.mean(self.zeiten) * 1000 if self.zeiten else 0
        return (f"  {self.name:26} n={self.anzahl:5}  "
                f"Mittel {mittel:7.1f} ms  "
                f"p50 {self.perzentil(0.50)*1000:7.1f}  "
                f"p95 {self.perzentil(0.95)*1000:7.1f}  "
                f"p99 {self.perzentil(0.99)*1000:7.1f}  "
                f"Fehler {self.fehlerquote*100:5.1f} %")


class Lasttest:
    def __init__(self, server: str, nutzer: int, runden: int, sammlung: int):
        self.server = server.rstrip("/")
        self.nutzer_anzahl = nutzer
        self.runden = runden
        self.sammlung_groesse = sammlung
        self.messungen: Dict[str, Messung] = {}
        self.token: Dict[str, str] = {}

    def messung(self, name: str) -> Messung:
        return self.messungen.setdefault(name, Messung(name))

    async def _ruf(self, client: httpx.AsyncClient, name: str, methode: str,
                   pfad: str, token: Optional[str] = None, **kwargs) -> Optional[dict]:
        kopf = kwargs.pop("headers", {})
        if token:
            kopf["Authorization"] = f"Bearer {token}"
        m = self.messung(name)
        start = time.perf_counter()
        try:
            antwort = await client.request(methode, self.server + pfad, headers=kopf, **kwargs)
        except Exception as fehler:
            m.fehlschlag(type(fehler).__name__)
            return None
        dauer = time.perf_counter() - start
        if antwort.status_code >= 400:
            m.fehlschlag(f"HTTP {antwort.status_code}")
            return None
        m.erfolg(dauer)
        try:
            return antwort.json()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Vorbereitung
    # ------------------------------------------------------------------
    async def anmelden(self, client: httpx.AsyncClient, nummer: int) -> Optional[str]:
        name = f"last-{nummer}"
        passwort = "Lasttest-Passwort-123"
        await client.post(f"{self.server}/api/register", json={
            "benutzername": name, "passwort": passwort,
            "email": f"{name}@lasttest.invalid"})
        antwort = await client.post(f"{self.server}/api/login", json={
            "benutzername": name, "passwort": passwort})
        daten = antwort.json()
        token = daten.get("access_token")
        if token:
            self.token[name] = token
        return token

    async def cache_waermen(self, client: httpx.AsyncClient) -> None:
        """Karten einmal holen, damit die Messung nicht Scryfall misst."""
        print("Wärme den Kartencache ...", flush=True)
        for karte in TESTKARTEN:
            await client.get(f"{self.server}/api/suche/{karte}")
        # Auch die Deckkarten, damit Stats/Manabasis aus dem Cache kommen.
        erster = next(iter(self.token.values()), None)
        if erster:
            await client.post(f"{self.server}/api/deck/stats",
                              json={"deck_liste": TESTDECK},
                              headers={"Authorization": f"Bearer {erster}"})

    async def sammlung_fuellen(self, client: httpx.AsyncClient, benutzer: str,
                               anzahl: int) -> None:
        token = self.token[benutzer]
        for i in range(anzahl):
            karte = TESTKARTEN[i % len(TESTKARTEN)]
            await client.post(f"{self.server}/api/sammlung/hinzufuegen", json={
                "benutzername": benutzer, "karten_name": karte,
                "album_name": f"Ordner {i % 10}", "bild_url": "", "preis": "1.00"},
                headers={"Authorization": f"Bearer {token}"})

    # ------------------------------------------------------------------
    # Die eigentliche Last
    # ------------------------------------------------------------------
    async def nutzer_runde(self, client: httpx.AsyncClient, benutzer: str) -> None:
        """Was ein Nutzer in einer Sitzung typischerweise tut.

        Die Reihenfolge bildet die Oberflaeche nach: Sammlung oeffnen heisst
        Ordneruebersicht, dann einen Ordner aufschlagen -- und der laedt eine
        Seite, nicht alles. Wer hier den alten Rundum-Endpunkt misst, misst
        etwas, das die Seite gar nicht mehr aufruft.
        """
        token = self.token[benutzer]
        await self._ruf(client, "Kartensuche", "GET",
                        f"/api/suche/{TESTKARTEN[hash(benutzer) % len(TESTKARTEN)]}", token)
        await self._ruf(client, "Ordneruebersicht", "GET",
                        f"/api/sammlung/{benutzer}/uebersicht", token)
        await self._ruf(client, "Ordner aufschlagen", "GET",
                        f"/api/sammlung/{benutzer}/filter?album=Ordner+0&seite=1&pro_seite=100",
                        token)
        await self._ruf(client, "Decks anzeigen", "GET", f"/api/decks/{benutzer}", token)
        await self._ruf(client, "Deck-Statistik", "POST", "/api/deck/stats", token,
                        json={"deck_liste": TESTDECK})
        await self._ruf(client, "Farbquellen", "POST", "/api/deck/manabasis", token,
                        json={"deck_liste": TESTDECK})
        await self._ruf(client, "Sammlungsabgleich", "POST", "/api/deck/abgleich", token,
                        json={"deck_liste": TESTDECK})

    async def lauf(self) -> None:
        grenzen = httpx.Limits(max_connections=200, max_keepalive_connections=100)
        async with httpx.AsyncClient(timeout=60.0, limits=grenzen) as client:
            print(f"Melde {self.nutzer_anzahl} Testnutzer an ...", flush=True)
            for i in range(self.nutzer_anzahl):
                if not await self.anmelden(client, i):
                    print(f"  Nutzer last-{i} konnte sich nicht anmelden")
            if not self.token:
                print("Kein einziger Nutzer angemeldet -- läuft der Server?")
                return

            await self.cache_waermen(client)

            erster = f"last-0"
            if self.sammlung_groesse:
                print(f"Lege {self.sammlung_groesse} Karten für {erster} an ...", flush=True)
                start = time.perf_counter()
                await self.sammlung_fuellen(client, erster, self.sammlung_groesse)
                print(f"  gedauert: {time.perf_counter() - start:.1f} s")

            # Jeder Nutzer bekommt ein Deck, damit die Deckliste nicht leer ist.
            for benutzer, token in self.token.items():
                await client.post(f"{self.server}/api/decks/erstellen", json={
                    "benutzername": benutzer, "deck_name": "Lasttest",
                    "deck_liste": TESTDECK, "format": "standard"},
                    headers={"Authorization": f"Bearer {token}"})

            print(f"\nLast: {len(self.token)} gleichzeitige Nutzer x {self.runden} Runden",
                  flush=True)
            start = time.perf_counter()
            for runde in range(self.runden):
                await asyncio.gather(*[self.nutzer_runde(client, b) for b in self.token])
                if (runde + 1) % 5 == 0:
                    print(f"  Runde {runde + 1}/{self.runden}", flush=True)
            dauer = time.perf_counter() - start

        self.bericht(dauer)

    def bericht(self, dauer: float) -> None:
        aufrufe = sum(m.anzahl for m in self.messungen.values())
        fehler = sum(sum(m.fehler.values()) for m in self.messungen.values())

        print("\n" + "=" * 78)
        print(f"Dauer: {dauer:.1f} s | Aufrufe: {aufrufe} | "
              f"Durchsatz: {aufrufe / dauer:.1f} Anfragen/s | "
              f"Fehler: {fehler} ({fehler / aufrufe * 100 if aufrufe else 0:.2f} %)")
        print("=" * 78)
        for m in sorted(self.messungen.values(), key=lambda x: -x.perzentil(0.95)):
            print(m.zeile())
            for grund, anzahl in sorted(m.fehler.items(), key=lambda p: -p[1]):
                print(f"      {anzahl}x {grund}")
        print()

        langsam = [m for m in self.messungen.values() if m.perzentil(0.95) > 1.0]
        if langsam:
            print("Über 1 Sekunde bei 95 Prozent der Aufrufe:")
            for m in langsam:
                print(f"  {m.name}: p95 {m.perzentil(0.95):.2f} s")
        if fehler:
            print("ACHTUNG: Es gab Fehler. Ein Ausfall unter Last zeigt sich zuerst hier.")


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--server", default="http://localhost:8000")
    zerleger.add_argument("--nutzer", type=int, default=25,
                          help="gleichzeitige Nutzer (Standard 25)")
    zerleger.add_argument("--runden", type=int, default=10)
    zerleger.add_argument("--sammlung", type=int, default=0,
                          help="so viele Karten für den ersten Nutzer anlegen")
    args = zerleger.parse_args()

    test = Lasttest(args.server, args.nutzer, args.runden, args.sammlung)
    asyncio.run(test.lauf())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
