#!/usr/bin/env python3
"""werkzeuge/cache_auffrischen.py -- veraltete Karteneinträge gezielt nachladen.

Wozu das nötig ist
------------------
Kommt ein neues Feld in den Kartendaten dazu (zuletzt `produced_mana` für die
Farbquellen-Analyse), sind alle vorhandenen Cache-Einträge unvollständig. Im
laufenden Betrieb heilt sich das von selbst: pro Anfrage werden bis zu 25
veraltete Einträge im Hintergrund nachgezogen. Bei einer Sammlung mit tausenden
Karten dauert das aber Tage -- und bis dahin arbeitet die Analyse für diese
Karten mit dem Rückfall auf den Regeltext.

Dieses Werkzeug macht daraus einen einzelnen bewussten Durchlauf, den man nach
dem Ausrollen einmal startet.

Aufruf
------
    python -m werkzeuge.cache_auffrischen            # nur zählen, nichts tun
    python -m werkzeuge.cache_auffrischen --machen   # tatsächlich nachladen
    python -m werkzeuge.cache_auffrischen --machen --grenze 500

Ohne --machen wird nur berichtet. Das ist Absicht: der Durchlauf spricht mit
Scryfall, und wie viele Karten betroffen sind, will man vorher wissen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from typing import List, Tuple

# Import aus dem Projektverzeichnis erlauben, auch wenn direkt aufgerufen.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.scryfall import _fetch_uncached, _is_stale  # noqa: E402

# Pro Runde an Scryfall. Der Sammel-Endpunkt nimmt 75 Namen; die Bibliothek
# drosselt zusätzlich selbst.
BUENDEL = 60


def cache_datei() -> str:
    return os.getenv("CACHE_DB_PATH", "scryfall_cache.db")


def veraltete_namen(pfad: str) -> Tuple[List[str], int]:
    """Liest die Cache-Datei und liefert (veraltete Namen, Gesamtzahl).

    Liest bewusst direkt aus SQLite: die Cache-Klasse kennt kein Auflisten, und
    für einen einmaligen Wartungslauf ist das der einfachste ehrliche Weg.
    """
    if not os.path.exists(pfad):
        return [], 0

    conn = sqlite3.connect(pfad)
    try:
        zeilen = conn.execute(
            "SELECT key, value FROM scryfall_cache WHERE key LIKE 'card:%'"
        ).fetchall()
    except sqlite3.Error as fehler:
        print(f"Cache nicht lesbar: {fehler}")
        return [], 0
    finally:
        conn.close()

    namen: List[str] = []
    gesehen = set()
    for key, roh in zeilen:
        try:
            eintrag = json.loads(roh)
        except (TypeError, ValueError):
            continue
        if not isinstance(eintrag, dict) or not _is_stale(eintrag):
            continue
        # Der kanonische Name aus dem Eintrag, nicht der Schlüssel: unter einem
        # Schlüssel können Schreibvarianten liegen.
        name = eintrag.get("name") or key.split("card:", 1)[-1]
        if name.lower() not in gesehen:
            gesehen.add(name.lower())
            namen.append(name)
    return namen, len(zeilen)


async def auffrischen(namen: List[str], grenze: int) -> int:
    """Lädt die Karten neu. Gibt die Zahl der bearbeiteten Namen zurück."""
    zu_tun = namen[:grenze] if grenze else namen
    erledigt = 0
    for start in range(0, len(zu_tun), BUENDEL):
        buendel = zu_tun[start:start + BUENDEL]
        try:
            # Bewusst _fetch_uncached statt fetch_card_details_cached: letzteres
            # findet die (veralteten) Einträge im Cache, liefert sie aus und
            # stellt das Nachladen nur in den Hintergrund -- dieser Prozess wäre
            # vorher beendet. Hier soll wirklich gegen Scryfall geladen und
            # geschrieben werden.
            await _fetch_uncached(buendel)
        except Exception as fehler:  # pragma: no cover -- Netzwerkfehler
            print(f"  Bündel ab {start} fehlgeschlagen: {type(fehler).__name__}: {fehler}")
            continue
        erledigt += len(buendel)
        print(f"  {erledigt}/{len(zu_tun)} nachgeladen", flush=True)
    return erledigt


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--machen", action="store_true",
                          help="tatsächlich nachladen (ohne dies wird nur gezählt)")
    zerleger.add_argument("--grenze", type=int, default=0,
                          help="höchstens so viele Karten nachladen (0 = alle)")
    args = zerleger.parse_args()

    pfad = cache_datei()
    namen, gesamt = veraltete_namen(pfad)

    print(f"Cache: {pfad}")
    print(f"Einträge insgesamt: {gesamt}")
    print(f"Davon veraltet:     {len(namen)}")

    if not namen:
        print("Nichts zu tun.")
        return 0

    if not args.machen:
        beispiele = ", ".join(namen[:5])
        print(f"Beispiele: {beispiele}")
        print("\nZum Nachladen: python -m werkzeuge.cache_auffrischen --machen")
        return 0

    print(f"\nLade nach (Bündel zu {BUENDEL}) ...")
    erledigt = asyncio.run(auffrischen(namen, args.grenze))

    rest, _ = veraltete_namen(pfad)
    print(f"\nFertig: {erledigt} Karten bearbeitet, noch veraltet: {len(rest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
