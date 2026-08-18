#!/usr/bin/env python3
"""werkzeuge/ki_kosten.py -- was kostet ein Nutzer wirklich?

Wozu
----
Die Abrechnung bei Google zeigt eine Summe. Daraus lässt sich nicht ablesen,
was EIN Nutzer kostet, wenn er seine Monatsgrenzen ausschöpft -- dafür müsste
man wissen, aus welcher Mischung von Aufrufen die Summe entstanden ist.

Dieses Werkzeug ruft jede KI-Funktion genau einmal auf, liest die echten
Tokenzahlen aus der Antwort und rechnet auf die Monatsgrenzen hoch. Am Ende
steht die Zahl, die zählt: **was ein Premium-Nutzer im schlimmsten Fall
kostet** -- und ob das unter dem Abo-Preis liegt.

Gemessen statt geschätzt
------------------------
Aufgerufen werden die ECHTEN Endpunkte über TestClient, nicht nachgebaute
Prompts. Damit fliesst alles mit ein, was die Prompts in Wirklichkeit gross
macht: der Regelauszug beim Judge, die aufgelösten Kartendaten bei der
Deck-Analyse, die tatsächliche Bildauflösung bei Live-Vision.

Voraussetzungen
---------------
    GEMINI_API_KEY              muss gesetzt sein (echte Aufrufe, echte Kosten)
    GEMINI_PRICE_INPUT_PER_MTOK optional -- ohne Preise nur Tokenzahlen
    GEMINI_PRICE_OUTPUT_PER_MTOK

Die Preise stehen in deiner Gemini-Preisliste. Ohne sie rechnet das Werkzeug
KEINEN Betrag aus -- ein geratener Preis wäre schlimmer als gar keiner.

Aufruf
------
    GEMINI_API_KEY=... python -m werkzeuge.ki_kosten
    GEMINI_API_KEY=... python -m werkzeuge.ki_kosten --abo 3.90 --waehrung CHF

Der Lauf kostet ein knappes Dutzend Gemini-Aufrufe, also Bruchteile eines
Rappens. Er legt eine eigene Wegwerf-Datenbank an und rührt deine Daten nicht
an.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Monatsgrenzen aus dem Produktivcode -- nicht hier noch einmal hinschreiben,
# sonst rechnet das Werkzeug irgendwann etwas anderes als die Anwendung tut.
from services.usage_limiter import (  # noqa: E402
    MONTHLY_SEARCH_LIMIT, MONTHLY_TEXT_LIMIT, MONTHLY_VISION_MINUTES_LIMIT,
)
from routers.vision import VISION_WS_MIN_GEMINI_INTERVAL_SECONDS  # noqa: E402

TESTNUTZER = "kostenmessung"

# Eine echte Regelfrage, kein "Hallo" -- der Judge hängt einen Regelauszug an,
# und dessen Grösse hängt an der Frage.
JUDGE_FRAGE = ("Mein Gegner blockt meine Kreatur mit Trample und Deathtouch. "
               "Wie viel Schaden darf ich dem Spieler zuweisen?")

# Ein Commander-Deck, wie es wirklich aussieht. Die Deck-Analyse löst jede
# Karte bei Scryfall auf und legt die Fakten in den Prompt -- ein Deck aus
# fünf Karten würde die Kosten deutlich zu niedrig ausweisen.
TESTDECK = "\n".join(
    ["1 Atraxa, Praetors' Voice"]
    + [f"1 {name}" for name in [
        "Sol Ring", "Command Tower", "Arcane Signet", "Cultivate", "Kodama's Reach",
        "Swords to Plowshares", "Path to Exile", "Counterspell", "Cyclonic Rift",
        "Rhystic Study", "Smothering Tithe", "Doubling Season", "Vorinclex, Monstrous Raider",
        "Deepglow Skate", "Contagion Engine", "Inexorable Tide", "Astral Cornucopia",
        "Everflowing Chalice", "Sage of Hours", "Fathom Mage", "Forgotten Ancient",
        "Kalonian Hydra", "Hardened Scales", "Corpsejack Menace", "Winding Constrictor",
    ]]
    + ["10 Forest", "10 Island", "10 Plains", "10 Swamp",
       "10 Mountain", "5 Evolving Wilds"]
)

# Ein deutscher Kartenname, den Scryfall nicht direkt findet -- das löst die
# sprachunabhängige Suche und damit ihre zwei Modellaufrufe aus.
SUCHBEGRIFF = "Blitzschlag Zauberspruch Karte"


# ======================================================================
# Wegwerf-Umgebung
# ======================================================================
@asynccontextmanager
async def _umgebung():
    """Eigene Datenbank mit einem Premium-Konto. Rührt echte Daten nicht an."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    macher = async_sessionmaker(engine, expire_on_commit=False)
    async with macher() as s:
        await s.execute(text(
            "INSERT INTO nutzer (benutzername, passwort_hash, rolle) "
            "VALUES (:n, 'x', 'premium')"), {"n": TESTNUTZER})
        await s.commit()

    @asynccontextmanager
    async def _sitzung():
        async with macher() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    with patch("database.get_db_session", _sitzung), \
            patch("routers.ai.get_db_session", _sitzung), \
            patch("routers.decks.get_db_session", _sitzung), \
            patch("routers.cards.get_db_session", _sitzung):
        yield macher
    await engine.dispose()


def _testbild() -> bytes:
    """Ein JPEG in genau der Auflösung und Qualität, die die App sendet.

    MobileCamera.jsx nimmt 1280x720 bei Qualität 0.65. Bilder rechnet Gemini
    nach Kacheln ab -- ein kleineres Testbild wiese die Kosten zu niedrig aus.
    """
    import cv2
    import numpy as np

    bild = np.random.randint(40, 210, (720, 1280, 3), dtype=np.uint8)
    # Ein paar kartenähnliche Rechtecke: ein reines Rauschbild komprimiert
    # anders als eine echte Aufnahme.
    for x in range(60, 1100, 200):
        cv2.rectangle(bild, (x, 200), (x + 150, 420), (230, 225, 210), -1)
    erfolg, puffer = cv2.imencode(".jpg", bild, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
    if not erfolg:
        raise RuntimeError("Testbild konnte nicht erzeugt werden")
    return puffer.tobytes()


# ======================================================================
# Messen
# ======================================================================
async def _messe(macher) -> None:
    """Ruft jede KI-Funktion einmal auf. Die Protokollierung zählt mit."""
    from fastapi.testclient import TestClient
    from auth import create_access_token
    from main import app

    kopf = {"Authorization": f"Bearer {create_access_token({'sub': TESTNUTZER})}"}
    bild = _testbild()
    print(f"Testbild: {len(bild)/1024:.0f} KB (1280x720, Qualität 65)\n")

    with TestClient(app) as client:
        schritte = [
            ("Judge", lambda: client.post(
                "/api/judge", json={"frage": JUDGE_FRAGE}, headers=kopf)),
            ("Deck-Analyse", lambda: client.post(
                "/api/deck/analyse",
                json={"deck_liste": TESTDECK, "format": "commander"}, headers=kopf)),
            ("Deck-Roast", lambda: client.post(
                "/api/deck/roast",
                json={"deck_liste": TESTDECK, "format": "commander"}, headers=kopf)),
            ("Kartensuche (Sprache)", lambda: client.get(
                f"/api/suche/{SUCHBEGRIFF}", headers=kopf)),
        ]
        for name, aufruf in schritte:
            print(f"  {name} ...", end=" ", flush=True)
            try:
                antwort = aufruf()
                print(f"HTTP {antwort.status_code}")
            except Exception as fehler:
                print(f"Fehler: {type(fehler).__name__}: {fehler}")

        # Live-Vision läuft über WebSocket: ein Bild rein, ein Ergebnis raus.
        print("  Live-Vision ...", end=" ", flush=True)
        try:
            token = create_access_token({"sub": TESTNUTZER})
            with client.websocket_connect(f"/api/vision/ws?token={token}") as ws:
                ws.send_bytes(bild)
                ws.receive_json()
            print("ok")
        except Exception as fehler:
            print(f"Fehler: {type(fehler).__name__}: {fehler}")

    # Das Protokoll wird gepuffert und von einer Hintergrundaufgabe
    # weggeschrieben. Hier einmal ausdruecklich leeren, sonst fehlen die
    # zuletzt gemessenen Aufrufe in der Auswertung.
    from sqlalchemy import text
    from services import ai_usage_log
    await ai_usage_log.flush()

    async with macher() as s:
        vorhanden = (await s.execute(
            text("SELECT COUNT(*) FROM ai_calls"))).scalar() or 0
    print(f"\n{vorhanden} Aufrufe protokolliert.\n")


async def _auswerten(macher) -> List[dict]:
    from sqlalchemy import text

    async with macher() as s:
        res = await s.execute(text(
            "SELECT funktion, modell, erfolg, prompt_tokens, antwort_tokens, "
            "gesamt_tokens, fehler FROM ai_calls ORDER BY id"))
        return [dict(r) for r in res.mappings().all()]


# ======================================================================
# Rechnen
# ======================================================================
def _preise() -> Tuple[Optional[float], Optional[float]]:
    def lies(name):
        roh = os.getenv(name)
        if not roh:
            return None
        try:
            return float(roh.replace(",", "."))
        except ValueError:
            return None
    return lies("GEMINI_PRICE_INPUT_PER_MTOK"), lies("GEMINI_PRICE_OUTPUT_PER_MTOK")


def _kosten(ein: Optional[int], aus: Optional[int],
            preis_ein: Optional[float], preis_aus: Optional[float]) -> Optional[float]:
    if preis_ein is None and preis_aus is None:
        return None
    summe = 0.0
    if preis_ein is not None:
        summe += (ein or 0) / 1_000_000 * preis_ein
    if preis_aus is not None:
        summe += (aus or 0) / 1_000_000 * preis_aus
    return summe


def _bericht(zeilen: List[dict], abo: Optional[float], waehrung: str) -> int:
    preis_ein, preis_aus = _preise()
    hat_preise = preis_ein is not None or preis_aus is not None

    erfolgreich = [z for z in zeilen if z["erfolg"] and z["gesamt_tokens"]]
    gescheitert = [z for z in zeilen if not z["erfolg"]]

    print("=" * 78)
    print("Gemessene Aufrufe")
    print("=" * 78)
    print(f"{'Funktion':<26} {'Modell':<24} {'Eingabe':>9} {'Ausgabe':>9}")
    for z in zeilen:
        if not z["erfolg"]:
            print(f"{z['funktion']:<26} {str(z['modell'] or '')[:24]:<24} "
                  f"{'-- gescheitert':>19}")
            continue
        print(f"{z['funktion']:<26} {str(z['modell'] or '')[:24]:<24} "
              f"{z['prompt_tokens'] or 0:>9,} {z['antwort_tokens'] or 0:>9,}"
              .replace(",", "."))

    if gescheitert:
        print()
        for z in gescheitert:
            print(f"  {z['funktion']}: {str(z['fehler'])[:120]}")

    if not erfolgreich:
        print("\nKein einziger Aufruf ist durchgekommen -- ist GEMINI_API_KEY "
              "gültig und Guthaben vorhanden?")
        return 1

    # --- Hochrechnung ---
    je_funktion: Dict[str, dict] = {}
    for z in erfolgreich:
        je_funktion.setdefault(z["funktion"], z)

    def tokens(*namen) -> Tuple[int, int]:
        for name in namen:
            z = je_funktion.get(name)
            if z:
                return int(z["prompt_tokens"] or 0), int(z["antwort_tokens"] or 0)
        return 0, 0

    # Das Text-Kontingent kann der Nutzer frei verteilen. Angesetzt wird
    # deshalb der TEUERSTE gemessene Aufruf -- eine Rechnung mit dem
    # Durchschnitt würde die Obergrenze schönfärben.
    #
    # Vision und Suche haben eigene Kontingente und stehen weiter unten; sie
    # dürfen hier nicht mitgezählt werden, sonst stünden sie doppelt drin.
    EIGENE_KONTINGENTE = {"vision_erkennung", "vision_rat", "karte_erkennen",
                          "kartenname_uebersetzung", "kartenname_auswahl"}
    text_aufrufe = [z for z in erfolgreich if z["funktion"] not in EIGENE_KONTINGENTE]
    if text_aufrufe:
        schlimmster = max(text_aufrufe,
                          key=lambda z: (z["prompt_tokens"] or 0) + (z["antwort_tokens"] or 0))
    else:
        schlimmster = {"funktion": "keiner gemessen", "prompt_tokens": 0, "antwort_tokens": 0}

    vision_intervalle = int(MONTHLY_VISION_MINUTES_LIMIT * 60
                            / VISION_WS_MIN_GEMINI_INTERVAL_SECONDS)

    bild_ein, bild_aus = tokens("vision_erkennung")
    rat_ein, rat_aus = tokens("vision_rat")

    # Eine Suche löst ZWEI verschiedene Aufrufe aus (Namen vorschlagen, dann
    # aus echten Namen wählen) -- mit unterschiedlich grossen Prompts. Beide
    # einzeln nehmen statt einen zu verdoppeln.
    such_ein, such_aus = 0, 0
    for name in ("kartenname_uebersetzung", "kartenname_auswahl"):
        e, a = tokens(name)
        such_ein += e
        such_aus += a

    print()
    print("=" * 78)
    print("Hochrechnung auf einen Premium-Nutzer, der alles ausschöpft")
    print("=" * 78)
    posten = [
        (f"{MONTHLY_TEXT_LIMIT}x Text ({schlimmster['funktion']}, teuerster gemessener)",
         MONTHLY_TEXT_LIMIT,
         int(schlimmster["prompt_tokens"] or 0), int(schlimmster["antwort_tokens"] or 0)),
        (f"{vision_intervalle}x Live-Vision Bilderkennung", vision_intervalle,
         bild_ein, bild_aus),
        (f"{vision_intervalle}x Live-Vision Taktikhinweis", vision_intervalle,
         rat_ein, rat_aus),
        (f"{MONTHLY_SEARCH_LIMIT}x Kartensuche (je 2 Aufrufe)",
         MONTHLY_SEARCH_LIMIT, such_ein, such_aus),
    ]

    gesamt_ein = gesamt_aus = 0
    gesamt_kosten = 0.0
    print(f"{'Posten':<52} {'Eingabe':>11} {'Ausgabe':>11}"
          + (f" {'Kosten':>10}" if hat_preise else ""))
    for name, anzahl, ein, aus in posten:
        s_ein, s_aus = ein * anzahl, aus * anzahl
        gesamt_ein += s_ein
        gesamt_aus += s_aus
        zeile = f"{name:<52} {s_ein:>11,} {s_aus:>11,}".replace(",", ".")
        k = _kosten(s_ein, s_aus, preis_ein, preis_aus)
        if k is not None:
            gesamt_kosten += k
            zeile += f" {k:>9.4f}"
        print(zeile)

    print("-" * 78)
    print(f"{'Summe':<52} {gesamt_ein:>11,} {gesamt_aus:>11,}".replace(",", ".")
          + (f" {gesamt_kosten:>9.4f}" if hat_preise else ""))

    print()
    if not hat_preise:
        print("Keine Preise hinterlegt -- deshalb nur Tokenzahlen.")
        print("Setze GEMINI_PRICE_INPUT_PER_MTOK und GEMINI_PRICE_OUTPUT_PER_MTOK")
        print("(Preis je 1 Mio. Tokens aus deiner Gemini-Preisliste) und lass den")
        print("Lauf erneut durchlaufen. Einen Preis zu raten wäre schlimmer als keiner.")
        return 0

    print(f"Ein Premium-Nutzer kostet dich im schlimmsten Fall "
          f"{gesamt_kosten:.2f} {waehrung} im Monat.")
    if abo is not None:
        marge = abo - gesamt_kosten
        print(f"Abo-Preis {abo:.2f} {waehrung} -> Marge {marge:.2f} {waehrung} "
              f"({marge / abo * 100:.0f} Prozent)" if abo else "")
        if marge < 0:
            print("\nACHTUNG: Du zahlst bei einem solchen Nutzer drauf.")
            return 2
        if marge < abo * 0.5:
            print("\nHinweis: Weniger als die Hälfte bleibt übrig -- vor Stripe-Gebühren.")
    else:
        print("Mit --abo <Betrag> rechnet das Werkzeug die Marge gleich mit aus.")

    print("\nHinweis: Bilder rechnet Gemini nach Kacheln ab. Ändert sich die")
    print("Auflösung in MobileCamera.jsx, ändert sich auch dieser Betrag.")
    return 0


def _protokoll_beruhigen() -> None:
    """Fremdbibliotheken leise stellen.

    Ohne das verschwindet die eigentliche Tabelle zwischen hunderten Zeilen
    HTTP-Protokoll -- und wer das Werkzeug zum ersten Mal benutzt, sieht vor
    lauter Technik das Ergebnis nicht. Warnungen der Anwendung selbst bleiben
    sichtbar: sie sagen, WARUM ein Aufruf gescheitert ist.
    """
    import logging

    for name in ("httpx", "httpcore", "google_genai", "google_genai.models",
                 "urllib3", "main", "services.cache", "services.rules_corpus",
                 "services.fehlermeldung", "services.ai_service",
                 "services.multilingual_search", "routers.ai", "routers.decks",
                 "routers.cards", "routers.vision"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


async def _lauf(abo: Optional[float], waehrung: str) -> int:
    _protokoll_beruhigen()
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY ist nicht gesetzt -- ohne echten Schlüssel gibt es")
        print("keine echten Tokenzahlen, und geschätzte wären wertlos.")
        return 1

    async with _umgebung() as macher:
        await _messe(macher)
        zeilen = await _auswerten(macher)
    return _bericht(zeilen, abo, waehrung)


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--abo", type=float, default=None,
                          help="Abo-Preis je Monat, um die Marge auszurechnen")
    zerleger.add_argument("--waehrung", default="CHF")
    args = zerleger.parse_args()
    return asyncio.run(_lauf(args.abo, args.waehrung))


if __name__ == "__main__":
    raise SystemExit(main())
