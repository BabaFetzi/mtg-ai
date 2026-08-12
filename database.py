import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, Integer, Text, Numeric, DateTime, ForeignKey, Boolean, Index, text
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///mtg_app.db")

# Use aiosqlite for SQLite or asyncpg for PostgreSQL
# If it's a sqlite connection, we may need to disable check_same_thread
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args if connect_args else {}
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

class User(Base):
    __tablename__ = 'nutzer'
    benutzername = Column(String(50), primary_key=True)
    passwort_hash = Column(String(255))
    rolle = Column(String(20), default='free')
    
    # Extended fields
    email = Column(String(255), unique=True, nullable=True)
    oauth_provider = Column(String(20), nullable=True) # 'google', 'discord', NULL
    oauth_id = Column(String(255), nullable=True)
    erstellt_am = Column(DateTime, default=datetime.utcnow)
    letzter_login = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

class Collection(Base):
    __tablename__ = 'sammlung_alben'
    __table_args__ = (
        Index('idx_sammlung_user_album', 'benutzername', 'album_name'),
        Index('idx_sammlung_karten_name', 'karten_name'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    benutzername = Column(String(50), index=True)
    karten_name = Column(String(255), nullable=False)
    album_name = Column(String(100), default='Standard')
    bild_url = Column(Text, nullable=True)
    preis = Column(String(50), nullable=True) # Stored as string to match old schema
    
    # Extended fields
    scryfall_id = Column(String(36), nullable=True)
    edition = Column(String(20), nullable=True)
    seltenheit = Column(String(20), nullable=True)
    farben = Column(String(20), nullable=True) # 'W,U,B,R,G'
    manakosten = Column(Integer, nullable=True)
    kartentyp = Column(String(100), nullable=True)
    anzahl = Column(Integer, default=1)
    zustand = Column(String(20), default='NM')
    hinzugefuegt_am = Column(DateTime, default=datetime.utcnow)

class Deck(Base):
    __tablename__ = 'decks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    benutzername = Column(String(50), index=True)
    name = Column(String(100), nullable=False)
    liste = Column(Text, nullable=True)
    
    # Extended fields
    format = Column(String(30), default='commander')
    erstellt_am = Column(DateTime, default=datetime.utcnow)
    aktualisiert_am = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserSession(Base):
    __tablename__ = 'sessions'
    id = Column(String(36), primary_key=True)
    benutzername = Column(String(50), nullable=False, index=True)
    refresh_token = Column(String(255), unique=True, nullable=False)
    laeuft_ab = Column(DateTime, nullable=False)
    erstellt_am = Column(DateTime, default=datetime.utcnow)

class PasswortReset(Base):
    """Einmal-Token zum Zurücksetzen des Passworts.

    Gespeichert wird NUR der SHA-256-Hash des Tokens. Wer die Datenbank liest,
    kann daraus kein gültiges Token bauen -- dieselbe Überlegung wie beim
    Passwort selbst. Ein Eintrag ist genau einmal brauchbar (benutzt_am) und
    verfällt nach kurzer Zeit (laeuft_ab).
    """
    __tablename__ = 'passwort_resets'
    id = Column(Integer, primary_key=True, autoincrement=True)
    benutzername = Column(String(50), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    laeuft_ab = Column(DateTime, nullable=False)
    benutzt_am = Column(DateTime, nullable=True)
    erstellt_am = Column(DateTime, default=datetime.utcnow)


class SynergyJob(Base):
    __tablename__ = 'synergy_jobs'
    job_id = Column(String(36), primary_key=True)
    status = Column(String(20), default='processing') # 'processing', 'completed', 'failed'
    result = Column(Text, nullable=True) # JSON-serialized combos/recommendations
    erstellt_am = Column(DateTime, default=datetime.utcnow)

class ImportJob(Base):
    __tablename__ = 'import_jobs'
    job_id = Column(String(36), primary_key=True)
    status = Column(String(20), default='processing') # 'processing', 'completed', 'failed'
    result = Column(Text, nullable=True) # JSON-serialized result: {"imported": X, "failed": Y, "errors": [...]}
    error = Column(Text, nullable=True)
    erstellt_am = Column(DateTime, default=datetime.utcnow)

class AiCall(Base):
    """Protokoll jeder KI-Anfrage: Modell, Tokens, Latenz, Kosten, Erfolg.

    Ohne dieses Protokoll lässt sich die Antwortqualität nur raten -- man sieht
    weder, welche Funktion wie oft fehlschlägt, noch was sie kostet.

    Datenschutz: Frage- und Antworttext werden NUR gespeichert, wenn
    AI_LOG_CONTENT=true gesetzt ist (Standard: aus). Ohne das Flag enthält die
    Tabelle reine Betriebskennzahlen.
    """
    __tablename__ = 'ai_calls'
    id = Column(Integer, primary_key=True, autoincrement=True)
    benutzername = Column(String(50), index=True, nullable=True)
    funktion = Column(String(50), index=True)      # 'judge', 'deck_analyse', ...
    modell = Column(String(80))
    erfolg = Column(Boolean, default=True)
    fehler = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    antwort_tokens = Column(Integer, nullable=True)
    gesamt_tokens = Column(Integer, nullable=True)
    latenz_ms = Column(Integer, nullable=True)
    kosten_usd = Column(Numeric(12, 6), nullable=True)  # NULL, wenn keine Preise konfiguriert sind
    frage = Column(Text, nullable=True)            # nur mit AI_LOG_CONTENT=true
    antwort = Column(Text, nullable=True)          # nur mit AI_LOG_CONTENT=true
    erstellt_am = Column(DateTime, default=datetime.utcnow, index=True)

async def init_db():
    async with engine.begin() as conn:
        # Create tables if they do not exist
        await conn.run_sync(Base.metadata.create_all)
        # Explicitly create indexes for existing databases
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sammlung_user_album ON sammlung_alben (benutzername, album_name)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sammlung_karten_name ON sammlung_alben (karten_name)"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS import_jobs (job_id TEXT PRIMARY KEY, status TEXT, result TEXT, error TEXT, erstellt_am TIMESTAMP)"))

async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


import contextlib

@contextlib.asynccontextmanager
async def get_db_session():
    """
    Async Context Manager für DB-Sessions mit Auto-Commit/Rollback.

    Verwendung:
        async with get_db_session() as session:
            await session.execute(...)
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_user_premium(benutzername: str) -> bool:
    """Prüft ob ein Benutzer die Premium-Rolle hat."""
    if not benutzername:
        return False
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT rolle FROM nutzer WHERE benutzername = :name"),
                {"name": benutzername}
            )
            row = res.mappings().first()
            if row:
                return (row["rolle"] or "free") == "premium"
    except Exception:
        logger.exception("Error checking user role for %s", benutzername)
    return False
