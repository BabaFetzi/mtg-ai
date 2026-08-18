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
    GEMINI_API_KEY   muss gesetzt sein (es sind echte Aufrufe mit echten Kosten)
    GEMINI_PREISE    optional -- ohne Preise nur Tokenzahlen, keine Betraege

Die Preise stehen JE MODELL, weil die Anwendung zwei benutzt: das grosse fuer
die Deck-Analyse, das kleine fuer alles andere. Zwischen ihnen liegt laut
Preisliste Faktor 20 und mehr, ein Einheitspreis waere also grob falsch:

    GEMINI_PREISE=gemini-2.5-flash:0.30/2.50; gemini-2.5-flash-lite:0.10/0.40

Getrennt wird mit SEMIKOLON, nicht mit Komma -- das Komma ist das
deutsche Dezimalzeichen und wuerde "0,30" zerreissen.

Geschluesselt wird nach dem Modell, das TATSAECHLICH geantwortet hat -- nicht
nach dem angefragten Alias. Taucht ein Modell ohne hinterlegten Preis auf,
sagt das Werkzeug das und laesst es aus der Summe heraus, statt still mit
einem falschen Wert zu rechnen.

Aufruf
------
    python -m werkzeuge.ki_kosten
    python -m werkzeuge.ki_kosten --abo 3.90 --waehrung CHF --kurs 0.79

--kurs rechnet die hinterlegten Preise um: Googles Liste ist in USD, die
Abrechnung laeuft womoeglich in einer anderen Waehrung.

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

# ----------------------------------------------------------------------
# Eigener, leerer Zwischenspeicher -- MUSS vor den App-Importen stehen
# ----------------------------------------------------------------------
# Deck-Analyse und Deck-Roast legen ihr Ergebnis unter deck_analysis:<hash>
# bzw. deck_roast:<hash> im Kartencache ab (routers/decks.py), die Kartensuche
# ebenso. Der Cache liegt in einer DATEI, die zwischen zwei Laeufen liegen
# bleibt -- und das Testdeck ist immer dasselbe.
#
# Folge: der zweite Lauf beantwortete Deck-Analyse, Deck-Roast und Suche aus
# dem Cache, ohne Gemini auch nur anzufassen. HTTP 200 fuer alles, aber statt
# 9 nur noch 3 protokollierte Aufrufe -- und die Hochrechnung setzte fuer den
# teuersten Textaufruf den Judge an statt der Deck-Analyse. Das Ergebnis sah
# mit 0.72 CHF hervorragend aus und war das Gegenteil einer Messung.
#
# Ein Messwerkzeug darf nicht davon abhaengen, was zufaellig im Cache liegt.
# Deshalb bekommt jeder Lauf eine eigene, leere Cache-Datei (unten wieder
# geloescht) und benutzt ausdruecklich kein Redis -- sonst laege dasselbe
# Ergebnis dort.
import tempfile  # noqa: E402

_CACHE_DATEI = os.path.join(tempfile.gettempdir(),
                            f"grana_kostenmessung_{os.getpid()}.db")
os.environ["CACHE_DB_PATH"] = _CACHE_DATEI
os.environ["REDIS_URL"] = ""

# Monatsgrenzen aus dem Produktivcode -- nicht hier noch einmal hinschreiben,
# sonst rechnet das Werkzeug irgendwann etwas anderes als die Anwendung tut.
from services.usage_limiter import (  # noqa: E402
    MONTHLY_SEARCH_LIMIT, MONTHLY_TEXT_LIMIT, MONTHLY_VISION_MINUTES_LIMIT,
)
from services import umgebung  # noqa: E402
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
# Welcher Messschritt zu welcher protokollierten Funktion gehoert, und welche
# Cache-Eintraege vorher weg muessen, damit die Wiederholung wirklich bei
# Gemini landet statt im Zwischenspeicher.
WIEDERHOLBAR = {
    "Deck-Analyse": ("deck_analyse", "deck_analysis"),
    "Deck-Roast":   ("deck_roast",   "deck_roast"),
    "Judge":        ("judge",        None),
}


def _deck_cache_schluessel(praefix: str) -> str:
    """Derselbe Schluessel, den routers/decks.py bildet."""
    import hashlib

    deck_hash = hashlib.sha256(
        (TESTDECK.strip() + ":" + "commander").encode("utf-8")).hexdigest()
    return f"{praefix}:{deck_hash}"


async def _wiederhole_wo_ersatz(macher, schritte, versuche: int) -> None:
    """Wiederholt Schritte, bei denen nur das Ersatzmodell geantwortet hat."""
    from sqlalchemy import text as sql
    from services import ai_usage_log
    from services.cache import scryfall_cache

    nach_name = dict(schritte)

    for runde in range(max(0, versuche - 1)):
        await ai_usage_log.flush()
        async with macher() as s:
            res = await s.execute(sql(
                "SELECT funktion, modell, erfolg, prompt_tokens, antwort_tokens, "
                "gesamt_tokens, fehler FROM ai_calls ORDER BY id"))
            zeilen = [dict(r) for r in res.mappings().all()]

        # Welche Funktionen sind nur ueber den Ersatz durchgekommen?
        betroffen = set()
        for hinweis in _ersatz_hinweise(zeilen):
            for schritt, (funktion, _) in WIEDERHOLBAR.items():
                if f"'{funktion}'" in hinweis:
                    betroffen.add(schritt)
        if not betroffen:
            return

        for schritt in sorted(betroffen):
            _, cache_praefix = WIEDERHOLBAR[schritt]
            if cache_praefix:
                scryfall_cache.delete(_deck_cache_schluessel(cache_praefix))
            print(f"  {schritt} noch einmal (Versuch {runde + 2} von "
                  f"{versuche}, Hauptmodell war ausgefallen) ...",
                  end=" ", flush=True)
            try:
                antwort = nach_name[schritt]()
                print(f"HTTP {antwort.status_code}")
            except Exception as fehler:
                print(f"Fehler: {type(fehler).__name__}: {fehler}")


async def _messe(macher, versuche: int = 3) -> None:
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

        # --- Wo das Ersatzmodell eingesprungen ist, noch einmal versuchen ---
        # gemini-3.7-flash antwortet regelmaessig mit 503 ("high demand"). Die
        # Anwendung weicht dann auf das guenstige Ersatzmodell aus -- gemessen
        # wird also der billige Aufruf, und die Hochrechnung faellt zu niedrig
        # aus. Fuer die Planung braucht es aber den Normalfall, in dem das
        # angefragte Modell antwortet.
        #
        # Deshalb wird ein solcher Schritt wiederholt. Das Ergebnis liegt danach
        # im Cache, sonst kaeme die Wiederholung gar nicht bei Gemini an --
        # der Eintrag wird vorher geloescht.
        await _wiederhole_wo_ersatz(macher, schritte, versuche)

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
def _ersatz_hinweise(zeilen: List[dict]) -> List[str]:
    """Meldet Funktionen, die nur über das Ersatzmodell durchgekommen sind.

    Die Anwendung wiederholt einen gescheiterten Aufruf einmal mit dem
    Ersatzmodell. Beim teuren Modell ist der Ersatz das GÜNSTIGE -- die
    Messung erwischt dann den billigen Aufruf, und die Hochrechnung fällt zu
    niedrig aus.

    Woran das erkennbar ist: die Funktion ist einmal gescheitert und danach
    auf GENAU EINEM Modell gelungen. Kommt ein zweites, anderes Modell dazu
    (weil eine Wiederholung beim Hauptmodell durchkam), liegt eine echte
    Messung darauf vor und es gibt nichts mehr zu warnen.

    Die Namen lassen sich dafür ausdrücklich NICHT vergleichen: der
    gescheiterte Aufruf protokolliert den Alias ("gemini-flash-latest"), der
    gelungene das Modell, das wirklich geantwortet hat ("gemini-3.7-flash").
    Die beiden sind dasselbe und sehen völlig verschieden aus.
    """
    angefragt = {}
    for z in zeilen:
        if not z["erfolg"]:
            angefragt.setdefault(z["funktion"], str(z["modell"] or ""))

    gelungen_auf: Dict[str, List[str]] = {}
    for z in zeilen:
        if z["erfolg"]:
            modelle = gelungen_auf.setdefault(z["funktion"], [])
            if str(z["modell"] or "") not in modelle:
                modelle.append(str(z["modell"] or ""))

    hinweise = []
    for funktion, alias in angefragt.items():
        modelle = gelungen_auf.get(funktion, [])
        # Kein Erfolg -> das meldet die Fehlerliste, nicht diese Warnung.
        # Zwei verschiedene Modelle -> das Hauptmodell hat doch geantwortet.
        if len(modelle) != 1 or not alias or modelle[0] == alias:
            continue
        hinweise.append(
            f"\nACHTUNG: '{funktion}' ist nur über das ERSATZMODELL "
            f"durchgekommen.\n"
            f"  angefragt: {alias}  (ausgefallen)\n"
            f"  gerechnet: {modelle[0]}  (das Ersatzmodell, meist das günstigere)\n"
            f"Im Normalbetrieb antwortet das angefragte Modell -- dann ist der\n"
            f"echte Betrag HÖHER als hier ausgewiesen. Lass den Lauf später\n"
            f"noch einmal laufen, bis kein Ersatz mehr einspringt."
        )
    return hinweise


# Was ein vollstaendiger Lauf gemessen haben MUSS. Fehlt eine dieser
# Funktionen, ist die Hochrechnung unbrauchbar -- und zwar nach unten:
# der fehlende Posten geht mit null Kosten in die Summe ein.
#
# Das ist wirklich passiert. Deck-Analyse und Deck-Roast kamen aus dem Cache,
# also fehlten sie im Protokoll; fuer den teuersten Textaufruf setzte das
# Werkzeug daraufhin den Judge an (866 Tokens statt 2.521, dazu auf dem
# guenstigen Modell) und meldete 0.72 CHF bei 81 Prozent Marge. Eine Zahl,
# der man nichts ansieht.
ERWARTETE_MESSUNGEN = [
    ("Judge",                     ("judge",)),
    ("Deck-Analyse",              ("deck_analyse",)),
    ("Deck-Roast",                ("deck_roast",)),
    ("Live-Vision Bilderkennung", ("vision_erkennung", "karte_erkennen")),
    ("Live-Vision Taktikhinweis", ("vision_rat",)),
    ("Kartensuche",               ("kartenname_uebersetzung", "kartenname_auswahl",
                                   "kartentext_uebersetzung")),
]


def _fehlende_messungen(zeilen: List[dict]) -> List[str]:
    """Erwartete Funktionen, für die kein erfolgreicher Aufruf vorliegt."""
    gemessen = {z["funktion"] for z in zeilen
                if z["erfolg"] and (z["prompt_tokens"] or z["antwort_tokens"])}
    return [bezeichnung for bezeichnung, namen in ERWARTETE_MESSUNGEN
            if not any(n in gemessen for n in namen)]


def _geldwert(z) -> float:
    """Was ein Aufruf gekostet hat -- zum Vergleichen zweier Messungen.

    In GELD, nicht in Tokens: ein Aufruf mit weniger Tokens auf dem teuren
    Modell kostet mehr als einer mit mehr Tokens auf dem guenstigen.
    """
    from services.ai_preise import kosten as modellkosten

    k = modellkosten(z["prompt_tokens"], z["antwort_tokens"], z["modell"])
    # Ohne Preis nach Tokens vergleichen -- besser als gar keine Reihung.
    return k if k is not None else (
        ((z["prompt_tokens"] or 0) + (z["antwort_tokens"] or 0)) / 1e9)


def _bericht(zeilen: List[dict], abo: Optional[float], waehrung: str,
             kurs: float = 1.0) -> int:
    from services.ai_preise import kosten as modellkosten, preis_fuer, tabelle

    preistabelle = tabelle()
    hat_preise = bool(preistabelle)

    erfolgreich = [z for z in zeilen if z["erfolg"] and z["gesamt_tokens"]]
    gescheitert = [z for z in zeilen if not z["erfolg"]]

    print("=" * 78)
    print("Gemessene Aufrufe")
    print("=" * 78)
    print(f"{'Funktion':<26} {'Modell':<26} {'Eingabe':>9} {'Ausgabe':>9}")
    for z in zeilen:
        if not z["erfolg"]:
            print(f"{z['funktion']:<26} {str(z['modell'] or '')[:26]:<26} "
                  f"{'-- gescheitert':>19}")
            continue
        print(f"{z['funktion']:<26} {str(z['modell'] or '')[:26]:<26} "
              f"{format(z['prompt_tokens'] or 0, ',').replace(',', '.'):>9} "
              f"{format(z['antwort_tokens'] or 0, ',').replace(',', '.'):>9}")

    if gescheitert:
        print()
        for z in gescheitert:
            print(f"  {z['funktion']}: {str(z['fehler'])[:120]}")

    if not erfolgreich:
        print("\nKein einziger Aufruf ist durchgekommen -- ist GEMINI_API_KEY "
              "gültig und Guthaben vorhanden?")
        return 1

    # --- Hochrechnung ---
    # Je Funktion der TEUERSTE gelungene Aufruf, nicht der erste. Nach einer
    # Wiederholung liegen zwei Messungen vor -- die billige vom Ersatzmodell
    # und die vom Hauptmodell. Der erste Treffer waere die billige, und damit
    # haette die Wiederholung nichts gebracht.
    je_funktion: Dict[str, dict] = {}
    for z in erfolgreich:
        vorhanden = je_funktion.get(z["funktion"])
        if vorhanden is None or _geldwert(z) > _geldwert(vorhanden):
            je_funktion[z["funktion"]] = z

    def messung(*namen) -> Tuple[int, int, str]:
        """Tokens UND das Modell, das tatsächlich geantwortet hat."""
        for name in namen:
            z = je_funktion.get(name)
            if z:
                return (int(z["prompt_tokens"] or 0), int(z["antwort_tokens"] or 0),
                        str(z["modell"] or ""))
        return 0, 0, ""

    # Das Text-Kontingent kann der Nutzer frei verteilen. Angesetzt wird
    # deshalb der TEUERSTE gemessene Aufruf -- eine Rechnung mit dem
    # Durchschnitt würde die Obergrenze schönfärben.
    #
    # "Teuerster" heisst hier: in Geld, nicht in Tokens. Die Deck-Analyse
    # laeuft auf dem GROSSEN Modell, alles andere auf dem kleinen -- ein
    # Aufruf mit weniger Tokens kann also mehr kosten.
    EIGENE_KONTINGENTE = {"vision_erkennung", "vision_rat", "karte_erkennen",
                          "kartenname_uebersetzung", "kartenname_auswahl"}
    text_aufrufe = [z for z in erfolgreich if z["funktion"] not in EIGENE_KONTINGENTE]

    if text_aufrufe:
        schlimmster = max(text_aufrufe, key=_geldwert)
    else:
        schlimmster = {"funktion": "keiner gemessen", "prompt_tokens": 0,
                       "antwort_tokens": 0, "modell": ""}

    vision_intervalle = int(MONTHLY_VISION_MINUTES_LIMIT * 60
                            / VISION_WS_MIN_GEMINI_INTERVAL_SECONDS)

    bild_ein, bild_aus, bild_modell = messung("vision_erkennung")
    rat_ein, rat_aus, rat_modell = messung("vision_rat")

    # Eine Suche löst ZWEI verschiedene Aufrufe aus (Namen vorschlagen, dann
    # aus echten Namen wählen) -- mit unterschiedlich grossen Prompts. Beide
    # einzeln nehmen statt einen zu verdoppeln.
    such_ein, such_aus, such_modell = 0, 0, ""
    for name in ("kartenname_uebersetzung", "kartenname_auswahl"):
        e, a, m = messung(name)
        such_ein += e
        such_aus += a
        such_modell = such_modell or m

    print()
    print("=" * 78)
    print("Hochrechnung auf einen Premium-Nutzer, der alles ausschöpft")
    print("=" * 78)
    posten = [
        (f"{MONTHLY_TEXT_LIMIT}x Text ({schlimmster['funktion']}, teuerster)",
         MONTHLY_TEXT_LIMIT, int(schlimmster["prompt_tokens"] or 0),
         int(schlimmster["antwort_tokens"] or 0), str(schlimmster.get("modell") or "")),
        (f"{vision_intervalle}x Live-Vision Bilderkennung", vision_intervalle,
         bild_ein, bild_aus, bild_modell),
        (f"{vision_intervalle}x Live-Vision Taktikhinweis", vision_intervalle,
         rat_ein, rat_aus, rat_modell),
        (f"{MONTHLY_SEARCH_LIMIT}x Kartensuche (je 2 Aufrufe)",
         MONTHLY_SEARCH_LIMIT, such_ein, such_aus, such_modell),
    ]

    gesamt_ein = gesamt_aus = 0
    gesamt_kosten = 0.0
    ohne_preis = set()

    print(f"{'Posten':<44} {'Eingabe':>10} {'Ausgabe':>10}"
          + (f" {'Kosten':>11}" if hat_preise else ""))
    for name, anzahl, ein, aus, modell in posten:
        s_ein, s_aus = ein * anzahl, aus * anzahl
        gesamt_ein += s_ein
        gesamt_aus += s_aus
        # Tausendertrennung NUR auf den Zahlen: ein globales replace(",", ".")
        # traf auch die Kommas in der Beschriftung ("deck_analyse. teuerster").
        zeile = (f"{name:<44} {format(s_ein, ',').replace(',', '.'):>10} "
                 f"{format(s_aus, ',').replace(',', '.'):>10}")
        if hat_preise:
            k = modellkosten(s_ein, s_aus, modell)
            if k is None:
                if s_ein or s_aus:
                    ohne_preis.add(modell or "(unbekannt)")
                zeile += f" {'Preis fehlt':>11}"
            else:
                gesamt_kosten += k * kurs
                zeile += f" {k * kurs:>11.4f}"
        print(zeile)

    print("-" * 78)
    print(f"{'Summe':<44} {format(gesamt_ein, ',').replace(',', '.'):>10} "
          f"{format(gesamt_aus, ',').replace(',', '.'):>10}"
          + (f" {gesamt_kosten:>11.4f}" if hat_preise else ""))

    # --- Ist hier ein Ersatzmodell eingesprungen? ---
    # Faellt das Hauptmodell aus (503 "high demand"), wiederholt die Anwendung
    # den Aufruf mit dem Ersatzmodell -- und das ist beim teuren Modell das
    # GUENSTIGE. Gemessen wird dann der billige Aufruf, und die Hochrechnung
    # faellt zu niedrig aus, ohne dass man es der Zahl ansieht.
    #
    # Das ist genau die Richtung, in die man sich hier nicht irren darf: die
    # Zahl saehe beruhigend aus und waere falsch.
    for zeile_ersatz in _ersatz_hinweise(zeilen):
        print(zeile_ersatz)

    # --- Ist ueberhaupt jede Funktion gemessen worden? ---
    fehlend = _fehlende_messungen(zeilen)
    if fehlend:
        print()
        print("ACHTUNG: Für diese Funktionen liegt keine Messung vor:")
        for f in fehlend:
            print(f"  {f}")
        print("Sie gehen mit NULL in die Summe ein -- der echte Betrag ist also")
        print("höher. Häufigste Ursache: das Ergebnis kam aus dem Cache, statt")
        print("Gemini wirklich zu fragen.")

    if ohne_preis:
        print()
        print("ACHTUNG: Für diese Modelle ist kein Preis hinterlegt, sie fehlen")
        print("in der Summe -- der echte Betrag ist also HÖHER:")
        for m in sorted(ohne_preis):
            print(f"  {m}")
        print("\nDie Preise stehen unter ai.google.dev/gemini-api/docs/pricing.")
        print("Ergänze GEMINI_PREISE um diese Zeile (Werte eintragen):")
        vorlage = "; ".join(f"{m}:EINGABE/AUSGABE" for m in sorted(ohne_preis))
        vorhandene = "; ".join(f"{m}:{e}/{a}" for m, (e, a) in sorted(preistabelle.items())
                               if m != "*" and e is not None and a is not None)
        print(f"\n  GEMINI_PREISE={'; '.join(x for x in (vorhandene, vorlage) if x)}")

    print()
    if not hat_preise:
        print("Keine Preise hinterlegt -- deshalb nur Tokenzahlen.")
        print("Setze GEMINI_PRICE_INPUT_PER_MTOK und GEMINI_PRICE_OUTPUT_PER_MTOK")
        print("(Preis je 1 Mio. Tokens aus deiner Gemini-Preisliste) und lass den")
        print("Lauf erneut durchlaufen. Einen Preis zu raten wäre schlimmer als keiner.")
        return 0

    if ohne_preis:
        # Kein Urteil auf einer unvollstaendigen Summe. Eine Marge auszuweisen,
        # bei der ein Posten fehlt, waere die gefaehrlichste Ausgabe von allen:
        # sie sieht aus wie ein Ergebnis.
        print(f"KEIN ERGEBNIS: mindestens ein Posten fehlt in der Summe.")
        print(f"Die {gesamt_kosten:.2f} {waehrung} oben sind eine Untergrenze, "
              f"nicht die Antwort.")
        print("Trag die fehlenden Preise nach und lass den Lauf erneut laufen.")
        return 3

    if fehlend:
        # Dasselbe Prinzip wie beim fehlenden Preis, nur eine Stufe frueher:
        # eine fehlende MESSUNG geht mit null Kosten in die Summe ein und
        # verschiebt ausserdem, welcher Aufruf als "teuerster" gilt.
        print("KEIN ERGEBNIS: nicht jede KI-Funktion wurde gemessen.")
        print(f"Die {gesamt_kosten:.2f} {waehrung} oben sind eine Untergrenze, "
              f"nicht die Antwort.")
        print("Es fehlen: " + ", ".join(fehlend))
        return 3

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

    print("\nHinweise:")
    print("* Bilder rechnet Gemini nach Kacheln ab. Ändert sich die Auflösung")
    print("  in MobileCamera.jsx, ändert sich auch dieser Betrag.")
    if kurs == 1.0:
        print("* Googles Preisliste ist in USD. Läuft dein Konto in einer anderen")
        print("  Währung, rechne mit --kurs um (z.B. --kurs 0.79 --waehrung CHF).")
    else:
        print(f"* Gerechnet mit Umrechnungsfaktor {kurs} auf {waehrung}.")
    return 0


def modelle_auflisten() -> int:
    """Zeigt, welche Modelle DIESER Schlüssel wirklich benutzen darf.

    Der Grund für diese Funktion: Google schaltet fest versionierte Modelle
    für neue Schlüssel ab. "gemini-2.5-flash" existiert, steht in der
    Preisliste -- und antwortet trotzdem mit
    "404 no longer available to new users". Welche Fassung ein bestimmter
    Schlüssel benutzen darf, weiss nur die API selbst.

    Raten hilft hier nicht. Fragen schon.
    """
    from google import genai

    try:
        client = genai.Client(api_key=umgebung.roh("GEMINI_API_KEY"))
        modelle = list(client.models.list())
    except Exception as fehler:
        print(f"Modelliste nicht abrufbar: {fehler}")
        return 1

    brauchbar = []
    for m in modelle:
        aktionen = getattr(m, "supported_actions", None) or []
        if aktionen and "generateContent" not in aktionen:
            continue
        name = (getattr(m, "name", "") or "").replace("models/", "")
        if name:
            brauchbar.append(name)

    if not brauchbar:
        print("Der Schlüssel darf kein einziges Modell für generateContent nutzen.")
        return 1

    passend = sorted(n for n in brauchbar
                     if "flash" in n
                     and not any(x in n for x in ("preview", "tts", "audio", "image",
                                                  "live", "thinking", "exp")))

    # Die beiden Aliase, die die Anwendung standardmaessig benutzt, muessen in
    # jedem Fall dabei sein -- sie sind die einzigen Namen, hinter denen sich
    # die Abrechnung versteckt, und genau sie stehen nicht immer in der Liste.
    from services.ai_service import MODEL_LITE_NAME, MODEL_NAME
    for alias in (MODEL_NAME, MODEL_LITE_NAME):
        if alias and alias not in passend:
            passend.append(alias)

    print(f"{len(brauchbar)} Modelle sind gelistet, davon {len(passend)} aus der "
          f"Flash-Familie.\n")
    print("Aufgelistet heisst NICHT benutzbar: Google fuehrt aeltere Fassungen")
    print("weiter auf, beantwortet sie fuer neuere Schluessel aber mit")
    print('"404 no longer available to new users". Deshalb wird jede jetzt')
    print("einmal wirklich angefragt.\n")

    from services.ai_preise import preis_fuer

    # "Rechnet ab als" ist die wichtigste Spalte. Ein Alias wie
    # "gemini-flash-latest" ist nur ein Zeiger; abgerechnet und in ai_calls.modell
    # protokolliert wird das Modell, das wirklich geantwortet hat. Ohne diese
    # Spalte fragt man den Preis fuer einen Namen ab, den es in keiner
    # Preisliste gibt -- und bekommt "Preis fehlt", ohne den Grund zu sehen.
    print(f"{'Modell':<26} {'Antwortet':<12} {'Rechnet ab als':<26} Preis")
    print("-" * 78)
    funktioniert = []
    aufgeloest = {}
    ohne_preis = []
    for name in passend:
        echt = ""
        try:
            antwort = client.models.generate_content(model=name, contents="ok")
            echt = getattr(antwort, "model_version", None) or name
            zustand, geht = "ja", True
        except Exception as fehler:
            text = str(fehler)
            if "no longer available" in text:
                zustand, geht = "nein (alt)", False
            elif "404" in text or "NOT_FOUND" in text:
                zustand, geht = "nein (404)", False
            elif "503" in text or "UNAVAILABLE" in text:
                # Kein Urteil ueber das Modell: es ist gerade nur ueberlastet.
                zustand, geht = "gerade voll", False
            else:
                zustand, geht = "nein", False

        # Der Preis gehoert zum ABRECHNENDEN Modell, nicht zum angefragten.
        ein, aus = preis_fuer(echt or name)
        preis = f"{ein}/{aus}" if ein is not None and aus is not None else "-- fehlt"
        print(f"{name:<26} {zustand:<12} {echt or '--':<26} {preis}")
        if geht:
            funktioniert.append(name)
            aufgeloest[name] = echt
            if (ein is None or aus is None) and echt not in ohne_preis:
                ohne_preis.append(echt)

    if not funktioniert:
        print("\nKein einziges Modell hat geantwortet -- stimmt der Schluessel?")
        return 1

    # Was die Anwendung TATSAECHLICH benutzt -- das ist die Zeile, wegen der
    # man dieses Werkzeug aufruft.
    print("\nWas Grana gerade benutzt:")
    for zweck, alias in (("Deck-Analyse    (GEMINI_MODEL)     ", MODEL_NAME),
                         ("alles andere    (GEMINI_MODEL_LITE)", MODEL_LITE_NAME)):
        ziel = aufgeloest.get(alias)
        if ziel:
            print(f"  {zweck} {alias}  ->  {ziel}")
        else:
            print(f"  {zweck} {alias}  ->  hat nicht geantwortet, "
                  f"Preis darum unbekannt")

    if ohne_preis:
        print("\nFuer diese Modelle fehlt der Preis in GEMINI_PREISE:")
        for m in ohne_preis:
            print(f"  {m}")
        print("Nachsehen unter ai.google.dev/gemini-api/docs/pricing.")

    print("\nNimm fuer GEMINI_MODEL_LITE das guenstigste, das antwortet, und fuer")
    print("GEMINI_MODEL eines der groesseren. Trag den Preis des Modells ein,")
    print("das in der Spalte 'Rechnet ab als' steht -- nicht den des Alias.")
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


async def _lauf(abo: Optional[float], waehrung: str, kurs: float,
                versuche: int = 3) -> int:
    _protokoll_beruhigen()
    if not umgebung.roh("GEMINI_API_KEY"):
        print("GEMINI_API_KEY ist nicht gesetzt -- ohne echten Schlüssel gibt es")
        print("keine echten Tokenzahlen, und geschätzte wären wertlos.")
        return 1

    async with _umgebung() as macher:
        await _messe(macher, versuche)
        zeilen = await _auswerten(macher)
    return _bericht(zeilen, abo, waehrung, kurs)


def main() -> int:
    zerleger = argparse.ArgumentParser(
        description=__doc__,
        # Ohne das walzt argparse den Docstring zu einem Textblock --
        # Tabellen und Beispiele werden dabei unlesbar.
        formatter_class=argparse.RawDescriptionHelpFormatter)
    zerleger.add_argument("--abo", type=float, default=None,
                          help="Abo-Preis je Monat, um die Marge auszurechnen")
    zerleger.add_argument("--waehrung", default="CHF",
                          help="nur die Beschriftung der Betraege")
    zerleger.add_argument(
        "--kurs", type=float, default=1.0,
        help="Umrechnungsfaktor fuer die hinterlegten Preise. Googles "
             "Preisliste ist in USD, die Abrechnung laeuft in CHF -- mit "
             "--kurs 0.79 --waehrung CHF werden aus Dollarpreisen Franken.")
    zerleger.add_argument(
        "--modelle", action="store_true",
        help="nur auflisten, welche Modelle dieser Schluessel benutzen darf, "
             "und nichts messen")
    zerleger.add_argument(
        "--versuche", type=int, default=3, metavar="N",
        help="wie oft ein Schritt hoechstens wiederholt wird, wenn statt des "
             "Hauptmodells nur das Ersatzmodell geantwortet hat (Standard 3). "
             "gemini-3.7-flash meldet regelmaessig 503 'high demand' -- ohne "
             "Wiederholung wuerde die Hochrechnung auf dem guenstigen "
             "Ersatzmodell beruhen und zu niedrig ausfallen")
    args = zerleger.parse_args()
    try:
        if args.modelle:
            _protokoll_beruhigen()
            return modelle_auflisten()
        return asyncio.run(_lauf(args.abo, args.waehrung, args.kurs,
                                 args.versuche))
    finally:
        # Die Wegwerf-Cache-Datei nicht liegen lassen -- der naechste Lauf soll
        # ohnehin eine eigene bekommen, und im Temp-Ordner sammeln sie sich sonst an.
        for endung in ("", "-wal", "-shm"):
            try:
                os.remove(_CACHE_DATEI + endung)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
