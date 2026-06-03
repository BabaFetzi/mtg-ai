import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, String, Integer, Text, Numeric, DateTime, ForeignKey, Boolean
from datetime import datetime

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

class Collection(Base):
    __tablename__ = 'sammlung_alben'
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

async def init_db():
    async with engine.begin() as conn:
        # Create tables if they do not exist
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
