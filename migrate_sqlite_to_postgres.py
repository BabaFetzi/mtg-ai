import asyncio
import os
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database import Base, User, Collection, Deck
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = 'mtg_app.db'
POSTGRES_URL = os.getenv("DATABASE_URL")

if not POSTGRES_URL or POSTGRES_URL.startswith("sqlite"):
    print("WARNING: DATABASE_URL not set to PostgreSQL. Set DATABASE_URL to a postgresql connection string (e.g. postgresql+asyncpg://user:pass@host/db) to run this migration.")

async def migrate():
    if not POSTGRES_URL or POSTGRES_URL.startswith("sqlite"):
        print("Migration canceled: target database is not PostgreSQL.")
        return
        
    print(f"Connecting to target PostgreSQL: {POSTGRES_URL}")
    pg_engine = create_async_engine(POSTGRES_URL)
    pg_session_factory = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    
    # Initialize target schema
    async with pg_engine.begin() as conn:
        print("Creating PostgreSQL tables...")
        await conn.run_sync(Base.metadata.create_all)
        
    # Read from SQLite
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite file '{SQLITE_PATH}' not found. Nothing to migrate.")
        return
        
    print(f"Connecting to source SQLite: {SQLITE_PATH}")
    async with aiosqlite.connect(SQLITE_PATH) as sqlite_db:
        sqlite_db.row_factory = aiosqlite.Row
        
        # 1. Migrate Users
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM nutzer")
                sqlite_users = await cursor.fetchall()
                print(f"Found {len(sqlite_users)} users in SQLite.")
                
                for u in sqlite_users:
                    # Check if user already exists in PG
                    existing = await pg_session.get(User, u["benutzername"])
                    if not existing:
                        new_user = User(
                            benutzername=u["benutzername"],
                            passwort_hash=u["passwort_hash"],
                            rolle=u.get("rolle", "free")
                        )
                        pg_session.add(new_user)
            print("Users migration completed.")
            
        # 2. Migrate Sammlung
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM sammlung_alben")
                sqlite_coll = await cursor.fetchall()
                print(f"Found {len(sqlite_coll)} collection entries in SQLite.")
                
                for c in sqlite_coll:
                    new_entry = Collection(
                        benutzername=c["benutzername"],
                        karten_name=c["karten_name"],
                        album_name=c.get("album_name", "Standard"),
                        bild_url=c.get("bild_url"),
                        preis=c.get("preis")
                    )
                    pg_session.add(new_entry)
            print("Collection migration completed.")
            
        # 3. Migrate Decks
        async with pg_session_factory() as pg_session:
            async with pg_session.begin():
                cursor = await sqlite_db.execute("SELECT * FROM decks")
                sqlite_decks = await cursor.fetchall()
                print(f"Found {len(sqlite_decks)} decks in SQLite.")
                
                for d in sqlite_decks:
                    new_deck = Deck(
                        benutzername=d["benutzername"],
                        name=d["name"],
                        liste=d["liste"]
                    )
                    pg_session.add(new_deck)
            print("Decks migration completed.")

    print("Data migration SQLite -> PostgreSQL completed successfully.")

if __name__ == "__main__":
    asyncio.run(migrate())
