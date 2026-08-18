#!/usr/bin/env python3
"""werkzeuge/sicherung.py -- Datenbank sichern und zurückspielen.

Warum das nötig ist
-------------------
Eine Sammlung mit tausenden Karten ist Handarbeit von Jahren. Ohne Sicherung
reicht ein Plattenfehler, ein falscher Befehl oder ein misslungenes Update, und
sie ist weg -- mit ihr das Vertrauen aller zahlenden Kunden. Eine Sicherung,
die nie zurückgespielt wurde, ist dabei nur eine Vermutung: deshalb kann dieses
Werkzeug beides und prüft die erzeugte Datei gleich nach dem Schreiben.

Aufruf
------
    python -m werkzeuge.sicherung                      # sichern nach ./sicherungen
    python -m werkzeuge.sicherung --ziel /pfad         # anderes Verzeichnis
    python -m werkzeuge.sicherung --liste              # vorhandene Sicherungen
    python -m werkzeuge.sicherung --zuruecksichern DATEI

Täglich per Cron:
    0 3 * * *  cd /pfad/zur/app && python -m werkzeuge.sicherung >> sicherung.log 2>&1

SQLite wird über "VACUUM INTO" gesichert. Das erzeugt eine in sich stimmige
Kopie, auch wenn die App gerade schreibt -- ein einfaches Kopieren der Datei
kann mitten in einer Transaktion erwischt werden und ist dann unbrauchbar.
PostgreSQL wird über pg_dump gesichert.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import umgebung  # noqa: E402

STANDARD_ZIEL = "sicherungen"
# So viele Sicherungen bleiben liegen. Bei einem täglichen Lauf sind das zwei
# Wochen -- lange genug, um einen Fehler zu bemerken, der erst später auffällt.
BEHALTEN = 14


def datenbank_url() -> str:
    return umgebung.text("DATABASE_URL", "sqlite+aiosqlite:///mtg_app.db")


def ist_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def sqlite_pfad(url: str) -> str:
    """Dateipfad aus einer SQLAlchemy-URL.

    "sqlite+aiosqlite:///mtg_app.db"      -> "mtg_app.db"
    "sqlite+aiosqlite:////var/lib/app.db" -> "/var/lib/app.db"
    """
    ohne_schema = url.split(":///", 1)[-1]
    return ohne_schema or "mtg_app.db"


def zeitstempel() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def pg_dump_befehl(url: str, ziel: Path) -> List[str]:
    """Baut den pg_dump-Aufruf. Getrennt von der Ausführung, damit prüfbar."""
    # SQLAlchemy-Treiber im Schema entfernen: postgresql+asyncpg:// -> postgresql://
    bereinigt = url.replace("+asyncpg", "").replace("+psycopg2", "").replace("+psycopg", "")
    return ["pg_dump", "--no-owner", "--no-privileges", "--format=custom",
            "--file", str(ziel), bereinigt]


def sqlite_sichern(quelle: str, ziel: Path) -> None:
    """Stimmige Kopie über VACUUM INTO -- auch bei laufenden Schreibvorgängen."""
    conn = sqlite3.connect(quelle)
    try:
        # VACUUM INTO erwartet eine noch nicht existierende Datei.
        if ziel.exists():
            ziel.unlink()
        conn.execute("VACUUM INTO ?", (str(ziel),))
    finally:
        conn.close()


def sqlite_pruefen(datei: Path) -> Tuple[bool, str]:
    """Öffnet die Sicherung und prüft sie -- eine ungeprüfte ist eine Vermutung."""
    try:
        conn = sqlite3.connect(datei)
        try:
            ergebnis = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if ergebnis != "ok":
                return False, f"Integritätsprüfung: {ergebnis}"
            tabellen = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "nutzer" not in tabellen:
                return False, "Tabelle 'nutzer' fehlt -- das ist keine Grana-Datenbank"
            anzahl = conn.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0]
            return True, f"{len(tabellen)} Tabellen, {anzahl} Konten"
        finally:
            conn.close()
    except sqlite3.Error as fehler:
        return False, f"nicht lesbar: {fehler}"


def sichern(ziel_verzeichnis: str = STANDARD_ZIEL, url: Optional[str] = None) -> Path:
    """Legt eine Sicherung an und gibt ihren Pfad zurück."""
    url = url or datenbank_url()
    ordner = Path(ziel_verzeichnis)
    ordner.mkdir(parents=True, exist_ok=True)

    if ist_sqlite(url):
        quelle = sqlite_pfad(url)
        if not os.path.exists(quelle):
            raise FileNotFoundError(f"Datenbank {quelle} nicht gefunden")
        ziel = ordner / f"grana-{zeitstempel()}.db"
        sqlite_sichern(quelle, ziel)

        ok, meldung = sqlite_pruefen(ziel)
        if not ok:
            ziel.unlink(missing_ok=True)
            raise RuntimeError(f"Sicherung war fehlerhaft und wurde verworfen: {meldung}")
        print(f"Gesichert: {ziel} ({ziel.stat().st_size / 1024:.0f} kB, {meldung})")
        return ziel

    ziel = ordner / f"grana-{zeitstempel()}.dump"
    befehl = pg_dump_befehl(url, ziel)
    ergebnis = subprocess.run(befehl, capture_output=True, text=True)
    if ergebnis.returncode != 0:
        raise RuntimeError(f"pg_dump fehlgeschlagen: {ergebnis.stderr.strip()}")
    if not ziel.exists() or ziel.stat().st_size == 0:
        raise RuntimeError("pg_dump hat eine leere Datei erzeugt")
    print(f"Gesichert: {ziel} ({ziel.stat().st_size / 1024:.0f} kB)")
    return ziel


def sicherungen(ziel_verzeichnis: str = STANDARD_ZIEL) -> List[Path]:
    ordner = Path(ziel_verzeichnis)
    if not ordner.exists():
        return []
    dateien = [p for p in ordner.iterdir()
               if p.is_file() and p.name.startswith("grana-")]
    return sorted(dateien, key=lambda p: p.name, reverse=True)


def aufraeumen(ziel_verzeichnis: str = STANDARD_ZIEL, behalten: int = BEHALTEN) -> List[Path]:
    """Löscht die ältesten Sicherungen und gibt die gelöschten zurück."""
    alle = sicherungen(ziel_verzeichnis)
    zu_alt = alle[behalten:]
    for datei in zu_alt:
        datei.unlink(missing_ok=True)
    return zu_alt


def zuruecksichern(datei: str, url: Optional[str] = None) -> Path:
    """Spielt eine Sicherung zurück.

    Vom aktuellen Stand wird vorher eine Kopie angelegt. Wer eine falsche Datei
    erwischt, soll nicht auch noch den bisherigen Stand verloren haben.
    """
    url = url or datenbank_url()
    quelle = Path(datei)
    if not quelle.exists():
        raise FileNotFoundError(f"{datei} gibt es nicht")

    if not ist_sqlite(url):
        raise NotImplementedError(
            "Für PostgreSQL bitte pg_restore verwenden:\n"
            f"  pg_restore --clean --if-exists --no-owner -d <DATENBANK> {datei}")

    ok, meldung = sqlite_pruefen(quelle)
    if not ok:
        raise RuntimeError(f"Diese Sicherung ist unbrauchbar: {meldung}")

    ziel = Path(sqlite_pfad(url))
    if ziel.exists():
        vorher = ziel.with_name(f"{ziel.stem}-vor-ruecksicherung-{zeitstempel()}{ziel.suffix}")
        shutil.copy2(ziel, vorher)
        print(f"Bisheriger Stand gesichert unter: {vorher}")

    shutil.copy2(quelle, ziel)
    print(f"Zurückgespielt: {quelle} -> {ziel} ({meldung})")
    return ziel


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--ziel", default=STANDARD_ZIEL, help="Verzeichnis für Sicherungen")
    zerleger.add_argument("--behalten", type=int, default=BEHALTEN,
                          help=f"so viele Sicherungen behalten (Standard {BEHALTEN})")
    zerleger.add_argument("--liste", action="store_true", help="vorhandene Sicherungen zeigen")
    zerleger.add_argument("--zuruecksichern", metavar="DATEI",
                          help="diese Sicherung zurückspielen")
    args = zerleger.parse_args()

    if args.liste:
        vorhanden = sicherungen(args.ziel)
        if not vorhanden:
            print(f"Keine Sicherungen in {args.ziel}")
            return 0
        print(f"{len(vorhanden)} Sicherungen in {args.ziel}:")
        for datei in vorhanden:
            groesse = datei.stat().st_size / 1024
            print(f"  {datei.name}  ({groesse:.0f} kB)")
        return 0

    if args.zuruecksichern:
        zuruecksichern(args.zuruecksichern)
        return 0

    sichern(args.ziel)
    entfernt = aufraeumen(args.ziel, args.behalten)
    if entfernt:
        print(f"{len(entfernt)} alte Sicherungen entfernt (behalten: {args.behalten})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
