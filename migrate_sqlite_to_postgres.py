"""
migrate_sqlite_to_postgres.py – Einmalige Datenmigration SQLite -> PostgreSQL

Verwendung:
    DATABASE_URL=postgresql+asyncpg://user:pass@host/db python migrate_sqlite_to_postgres.py

Migriert nutzer, sammlung_alben und decks vollständig (inkl. aller
Erweiterungsfelder) von der lokalen SQLite-Datei nach PostgreSQL. Läuft
mehrfach sicher (idempotent): bereits migrierte Zeilen werden anhand ihres
Primärschlüssels übersprungen statt dupliziert.

Bewusst NICHT migriert:
    - sessions (Refresh-Tokens): sind kurzlebig und an den JWT_SECRET_KEY
      des Quellsystems gebunden. Nutzer melden sich nach der Migration
      einfach neu an.
    - synergy_jobs / import_jobs: transiente Hintergrund-Job-Zustände ohne
      Wert nach Abschluss der Migration.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import aiosqlite
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database import Base, User, Collection, Deck

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
from services import umgebung

logger = logging.getLogger("migrate_sqlite_to_postgres")

SQLITE_PATH = umgebung.text("SQLITE_PATH", "mtg_app.db")
POSTGRES_URL = umgebung.roh("DATABASE_URL")


def _parse_dt(value) -> Optional[datetime]:
    """SQLite speichert DateTime-Spalten als ISO-Text (oder NULL, wenn eine
    Zeile per Raw-SQL ohne den Wert eingefügt wurde -- der Normalfall in
    dieser App). asyncpg akzeptiert nur echte datetime-Objekte, kein Text."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        # Python < 3.11 / abweichendes Format: Leerzeichen-Separator statt "T"
        return datetime.fromisoformat(value.replace(" ", "T"))


async def _reset_sequence(conn, table: str, column: str = "id") -> None:
    """Nach expliziten ID-Inserts (zur Idempotenz/Referenztreue) steht die
    PostgreSQL-SERIAL-Sequenz sonst auf 1 und kollidiert beim nächsten
    autogenerierten Insert mit einer migrierten Zeile."""
    await conn.execute(text(
        f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
        f"COALESCE((SELECT MAX({column}) FROM {table}), 1), "
        f"(SELECT MAX({column}) FROM {table}) IS NOT NULL)"
    ))


async def migrate() -> None:
    if not POSTGRES_URL or POSTGRES_URL.startswith("sqlite"):
        logger.error(
            "DATABASE_URL ist nicht auf PostgreSQL gesetzt. Beispiel: "
            "DATABASE_URL=postgresql+asyncpg://user:pass@host/db"
        )
        return

    if not os.path.exists(SQLITE_PATH):
        logger.error("SQLite-Datei '%s' nicht gefunden. Nichts zu migrieren.", SQLITE_PATH)
        return

    logger.info("Ziel: PostgreSQL (%s)", POSTGRES_URL.split("@")[-1])
    pg_engine = create_async_engine(POSTGRES_URL)
    pg_session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with pg_engine.begin() as conn:
        logger.info("Erstelle PostgreSQL-Tabellen (falls nicht vorhanden)...")
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Quelle: SQLite (%s)", SQLITE_PATH)
    stats = {"nutzer": [0, 0], "sammlung_alben": [0, 0], "decks": [0, 0]}  # [migriert, uebersprungen]

    async with aiosqlite.connect(SQLITE_PATH) as sqlite_db:
        sqlite_db.row_factory = aiosqlite.Row

        # 1. Nutzer
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM nutzer")
                rows = [dict(r) for r in await cursor.fetchall()]
                logger.info("nutzer: %d Zeile(n) in SQLite gefunden.", len(rows))

                for r in rows:
                    existing = await pg_session.get(User, r["benutzername"])
                    if existing:
                        stats["nutzer"][1] += 1
                        continue
                    pg_session.add(User(
                        benutzername=r["benutzername"],
                        passwort_hash=r["passwort_hash"],
                        rolle=r.get("rolle") or "free",
                        email=r.get("email"),
                        oauth_provider=r.get("oauth_provider"),
                        oauth_id=r.get("oauth_id"),
                        erstellt_am=_parse_dt(r.get("erstellt_am")),
                        letzter_login=_parse_dt(r.get("letzter_login")),
                        stripe_customer_id=r.get("stripe_customer_id"),
                        stripe_subscription_id=r.get("stripe_subscription_id"),
                    ))
                    stats["nutzer"][0] += 1
            logger.info("nutzer: %d migriert, %d bereits vorhanden (übersprungen).", *stats["nutzer"])

        # 2. Sammlung (Karten-Alben)
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM sammlung_alben")
                rows = [dict(r) for r in await cursor.fetchall()]
                logger.info("sammlung_alben: %d Zeile(n) in SQLite gefunden.", len(rows))

                for r in rows:
                    existing = await pg_session.get(Collection, r["id"])
                    if existing:
                        stats["sammlung_alben"][1] += 1
                        continue
                    pg_session.add(Collection(
                        id=r["id"],
                        benutzername=r["benutzername"],
                        karten_name=r["karten_name"],
                        album_name=r.get("album_name") or "Standard",
                        bild_url=r.get("bild_url"),
                        preis=r.get("preis"),
                        scryfall_id=r.get("scryfall_id"),
                        edition=r.get("edition"),
                        seltenheit=r.get("seltenheit"),
                        farben=r.get("farben"),
                        manakosten=r.get("manakosten"),
                        kartentyp=r.get("kartentyp"),
                        anzahl=r.get("anzahl") if r.get("anzahl") is not None else 1,
                        zustand=r.get("zustand") or "NM",
                        hinzugefuegt_am=_parse_dt(r.get("hinzugefuegt_am")),
                    ))
                    stats["sammlung_alben"][0] += 1

            async with pg_engine.begin() as conn:
                await _reset_sequence(conn, "sammlung_alben")
            logger.info("sammlung_alben: %d migriert, %d bereits vorhanden (übersprungen).", *stats["sammlung_alben"])

        # 3. Decks
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM decks")
                rows = [dict(r) for r in await cursor.fetchall()]
                logger.info("decks: %d Zeile(n) in SQLite gefunden.", len(rows))

                for r in rows:
                    existing = await pg_session.get(Deck, r["id"])
                    if existing:
                        stats["decks"][1] += 1
                        continue
                    pg_session.add(Deck(
                        id=r["id"],
                        benutzername=r["benutzername"],
                        name=r["name"],
                        liste=r.get("liste"),
                        format=r.get("format") or "commander",
                        erstellt_am=_parse_dt(r.get("erstellt_am")),
                        aktualisiert_am=_parse_dt(r.get("aktualisiert_am")),
                    ))
                    stats["decks"][0] += 1

            async with pg_engine.begin() as conn:
                await _reset_sequence(conn, "decks")
            logger.info("decks: %d migriert, %d bereits vorhanden (übersprungen).", *stats["decks"])

    await pg_engine.dispose()

    total_migrated = sum(v[0] for v in stats.values())
    total_skipped = sum(v[1] for v in stats.values())
    logger.info(
        "Migration abgeschlossen: %d Zeile(n) migriert, %d bereits vorhanden übersprungen. "
        "sessions/synergy_jobs/import_jobs wurden absichtlich nicht migriert (siehe Modul-Docstring).",
        total_migrated, total_skipped,
    )


if __name__ == "__main__":
    asyncio.run(migrate())
