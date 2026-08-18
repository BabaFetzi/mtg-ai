"""
cleanup_alben.py – Einmal-Hilfsskript zum Aufräumen der Sammlung

Löscht alle Sammlungs-Alben AUSSER denen in KEEP (Standard: "Test").
Praktisch, um nach einem verunglückten CSV-Import die vielen automatisch
angelegten Alben (z.B. Set-Codes wie ECL, MAR, SPM, ...) auf einen Schlag
wieder loszuwerden.

Sicherheiten:
  * zeigt VORHER an, was behalten und was gelöscht wird
  * legt automatisch ein Backup der Datenbank an
  * löscht erst nach ausdrücklicher Bestätigung ("JA")

Ausführen (im mtg-ai Ordner, Backend vorher schließen!):
    python cleanup_alben.py
"""

import os
import shutil
import sqlite3
from datetime import datetime

from services import umgebung

# ----------------------------------------------------------------------------
# Einstellungen -- hier bei Bedarf anpassen
# ----------------------------------------------------------------------------
# Alben, die BEHALTEN werden sollen:
KEEP = {"Test"}
# Die Wunschliste ist ein eigenes Feature (eigener Tab) und wird sicherheits-
# halber ebenfalls behalten. Auf False setzen, wenn sie AUCH gelöscht werden soll.
KEEP_WISHLIST = True

# Pfad zur lokalen SQLite-Datenbank (Standard des Projekts).
DB_PATH = umgebung.text("SQLITE_PATH", "mtg_app.db")

TABLE = "sammlung_alben"


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"[Fehler] Datenbank '{DB_PATH}' nicht gefunden.")
        print("Bitte dieses Skript im 'mtg-ai'-Ordner ausfuehren.")
        return

    keep = set(KEEP)
    if KEEP_WISHLIST:
        keep.add("Wunschliste")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT album_name, COUNT(*) FROM {TABLE} GROUP BY album_name ORDER BY album_name"
        )
        rows = cur.fetchall()

        if not rows:
            print("Keine Alben in der Datenbank gefunden. Nichts zu tun.")
            return

        to_keep = [(n, c) for (n, c) in rows if n in keep]
        to_delete = [(n, c) for (n, c) in rows if n not in keep]

        print("\n================ VORSCHAU ================\n")
        print("BEHALTEN:")
        if to_keep:
            for name, cnt in to_keep:
                print(f"  [OK]  {name}  ({cnt} Karten/Eintraege)")
        else:
            print("  (keine der zu behaltenden Alben sind vorhanden!)")

        print("\nWIRD GELOESCHT:")
        if not to_delete:
            print("  (nichts -- es gibt keine weiteren Alben)")
            return
        for name, cnt in to_delete:
            print(f"  [X]   {name}  ({cnt} Karten/Eintraege)")

        total = sum(c for _, c in to_delete)
        print(f"\n=> {len(to_delete)} Alben mit insgesamt {total} Eintraegen werden geloescht.")
        print("==========================================\n")

        antwort = input('Zum Loeschen bitte  JA  eingeben (alles andere bricht ab): ').strip()
        if antwort != "JA":
            print("Abgebrochen. Es wurde NICHTS geloescht.")
            return

        # --- Sicherheits-Backup der kompletten Datenbank ---
        backup = f"{DB_PATH}.backup-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup angelegt: {backup}")

        placeholders = ",".join("?" for _ in keep)
        cur.execute(
            f"DELETE FROM {TABLE} WHERE album_name NOT IN ({placeholders})",
            tuple(keep),
        )
        deleted = cur.rowcount
        conn.commit()

        print(f"\nFertig! {deleted} Eintraege geloescht.")
        print("Lade die Sammlung im Browser neu (F5), um das Ergebnis zu sehen.")
        print(f"Falls doch etwas schiefging: die Datei '{backup}' ist deine Sicherung.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
