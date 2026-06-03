from fastapi import FastAPI, Request, UploadFile, File, Form, Query, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
import httpx
import urllib.parse
import aiosqlite
import hashlib
import os
import re
import csv
import io
import json
import stripe
from contextlib import asynccontextmanager, asynccontextmanager as ctx_asynccontextmanager
import contextlib
from dotenv import load_dotenv
from sqlalchemy import text
from database import init_db, async_session
from auth import (
    hash_passwort as bcrypt_hash,
    verify_passwort,
    create_access_token,
    create_refresh_token,
    get_current_user,
    check_login_rate_limit,
    record_login_attempt
)

# --- SICHERER KI-IMPORT ---
try:
    import google.generativeai as genai
    KI_VERFUEGBAR = True
except ImportError:
    print("\n" + "="*60)
    print("WARNUNG: Das Modul 'google-generativeai' fehlt!")
    print("Bitte führe im Terminal diesen Befehl aus: pip install google-generativeai")
    print("="*60 + "\n")
    genai = None
    KI_VERFUEGBAR = False

# --- UMWELTVARIABLEN LADEN ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# --- API CLIENT INITIALISIEREN ---
model = None
if KI_VERFUEGBAR and api_key:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print(f"FEHLER beim Initialisieren der KI: {e}")

# --- DATENBANK INITIALISIERUNG ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starte Datenbankverbindung...")
    try:
        await init_db()
        print("Datenbank erfolgreich initialisiert. Backend ist BEREIT!")
    except Exception as e:
        print(f"FEHLER bei der Datenbankinitialisierung: {e}")
    yield

@contextlib.asynccontextmanager
async def get_db_session():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

app = FastAPI(title="MTG App Pro Backend", lifespan=lifespan)

# --- CORS KONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"GLOBALER FEHLER: {exc}")
    return JSONResponse(status_code=500, content={"erfolg": False, "error": str(exc)})

# ==========================================
# 1. AUTHENTIFIZIERUNG
# ==========================================
class LoginData(BaseModel):
    benutzername: str
    passwort: str

def hash_passwort(passwort: str):
    return hashlib.sha256(str.encode(passwort)).hexdigest()

@app.post("/api/register")
async def register(data: LoginData):
    try:
        async with get_db_session() as session:
            # Check if user already exists
            res = await session.execute(
                text("SELECT benutzername FROM nutzer WHERE benutzername = :name"),
                {"name": data.benutzername}
            )
            if res.first():
                return {"erfolg": False, "error": "Benutzername schon vergeben."}
            
            # Hash password with bcrypt
            hashed = bcrypt_hash(data.passwort)
            await session.execute(
                text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES (:name, :pwhash, :role)"),
                {"name": data.benutzername, "pwhash": hashed, "role": "free"}
            )
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "error": str(e)}

@app.post("/api/login")
async def login(data: LoginData, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    # 1. Check rate limit
    try:
        check_login_rate_limit(ip, data.benutzername)
    except HTTPException as limit_exc:
        return {"erfolg": False, "error": limit_exc.detail}

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM nutzer WHERE benutzername = :name"),
            {"name": data.benutzername}
        )
        row = res.mappings().first()
        
        if not row:
            record_login_attempt(ip, data.benutzername, success=False)
            return {"erfolg": False, "error": "Falscher Benutzername oder Passwort."}
            
        stored_hash = row["passwort_hash"]
        is_valid = False
        migrate_hash = False
        
        # Check if stored hash is legacy SHA-256 (length 64) or bcrypt
        if stored_hash and len(stored_hash) == 64:
            legacy_hash = hashlib.sha256(str.encode(data.passwort)).hexdigest()
            if legacy_hash == stored_hash:
                is_valid = True
                migrate_hash = True
        else:
            if verify_passwort(data.passwort, stored_hash):
                is_valid = True
                
        if not is_valid:
            try:
                record_login_attempt(ip, data.benutzername, success=False)
            except HTTPException as block_exc:
                return {"erfolg": False, "error": block_exc.detail}
            return {"erfolg": False, "error": "Falscher Benutzername oder Passwort."}
            
        # Migrate hash if it was legacy SHA-256
        if migrate_hash:
            new_hash = bcrypt_hash(data.passwort)
            await session.execute(
                text("UPDATE nutzer SET passwort_hash = :new_hash WHERE benutzername = :name"),
                {"new_hash": new_hash, "name": data.benutzername}
            )
            
        # Record success
        record_login_attempt(ip, data.benutzername, success=True)
        
        # Generate JWT tokens
        token_data = {"sub": row["benutzername"], "role": row["rolle"] or "free"}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return {
            "erfolg": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "benutzername": row["benutzername"],
            "rolle": row["rolle"] or "free"
        }

@app.get("/api/user/role/{benutzername}")
async def get_user_role(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT rolle FROM nutzer WHERE benutzername = :name"),
            {"name": benutzername}
        )
        row = res.mappings().first()
        if row:
            return {"rolle": row["rolle"] or "free"}
        return {"rolle": "free"}

# ==========================================
# 2. KARTEN SUCHE (SCRYFALL API) & CACHING
# ==========================================
import time

class ScryfallCache:
    def __init__(self, ttl_seconds: int = 86400):
        self.ttl = ttl_seconds
        self.cache = {}

    def get(self, key: str):
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.ttl:
                return entry["data"]
            else:
                del self.cache[key]
        return None

    def set(self, key: str, data):
        self.cache[key] = {
            "timestamp": time.time(),
            "data": data
        }

scryfall_cache = ScryfallCache(ttl_seconds=86400)

async def fetch_card_details_cached(names: list) -> dict:
    scryfall_data = {}
    uncached_names = []
    
    for name in names:
        cache_key = f"card:{name.lower().strip()}"
        cached = scryfall_cache.get(cache_key)
        if cached:
            scryfall_data[name.lower().strip()] = cached
        else:
            # Also try cache lookup with just the front face if name has '//'
            front_key = name
            if "//" in name:
                front_key = name.split("//")[0].strip()
            cached_front = scryfall_cache.get(f"card:{front_key.lower().strip()}")
            if cached_front:
                scryfall_data[name.lower().strip()] = cached_front
                scryfall_data[front_key.lower().strip()] = cached_front
            else:
                uncached_names.append(name)
            
    if uncached_names:
        async with httpx.AsyncClient() as client:
            for i in range(0, len(uncached_names), 75):
                name_mapping = {}  # Maps cleaned search name to the original input name
                chunk = []
                for n in uncached_names[i:i+75]:
                    query_name = n
                    if "//" in n:
                        query_name = n.split("//")[0].strip()
                    query_name_clean = clean_card_name(query_name)
                    if query_name_clean:
                        name_mapping[query_name_clean.lower().strip()] = n
                        chunk.append({"name": query_name_clean})
                
                if not chunk:
                    continue
                    
                try:
                    resp = await client.post("https://api.scryfall.com/cards/collection", json={"identifiers": chunk})
                    if resp.status_code == 200:
                        data = resp.json()
                        for c in data.get("data", []):
                            img = c.get("image_uris", {}).get("normal", "")
                            if not img and "card_faces" in c:
                                img = c["card_faces"][0].get("image_uris", {}).get("normal", "")
                            
                            price_val = c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil") or "0.00"
                            
                            card_info = {
                                "name": c["name"],
                                "image": img,
                                "type": c.get("type_line", ""),
                                "cmc": c.get("cmc", 0.0),
                                "colors": c.get("colors", []),
                                "color_identity": c.get("color_identity", []),
                                "prices": c.get("prices", {}),
                                "price": price_val,
                                "legalities": c.get("legalities", {})
                            }
                            
                            c_name_lower = c["name"].lower().strip()
                            scryfall_cache.set(f"card:{c_name_lower}", card_info)
                            scryfall_data[c_name_lower] = card_info
                            
                            if "//" in c["name"]:
                                front_face = c["name"].split("//")[0].strip().lower()
                                scryfall_cache.set(f"card:{front_face}", card_info)
                                scryfall_data[front_face] = card_info
                                
                            for q_clean, orig_n in name_mapping.items():
                                if q_clean == c_name_lower or ( "//" in c["name"] and q_clean == c["name"].split("//")[0].strip().lower() ):
                                    scryfall_cache.set(f"card:{orig_n.lower().strip()}", card_info)
                                    scryfall_data[orig_n.lower().strip()] = card_info
                except Exception as e:
                    print(f"Error in collection fetch: {e}")
                    
                # Fallback for any names in this chunk that were not resolved by /cards/collection
                for identifier in chunk:
                    input_name = identifier["name"]
                    input_name_lower = input_name.lower().strip()
                    orig_n = name_mapping.get(input_name_lower, input_name)
                    orig_n_lower = orig_n.lower().strip()
                    
                    if orig_n_lower not in scryfall_data:
                        # Fallback 1: named?fuzzy=... (great for typos or missing punctuation)
                        try:
                            url_fuzzy = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(input_name)}"
                            resp_f = await client.get(url_fuzzy)
                            if resp_f.status_code == 200:
                                c = resp_f.json()
                                img = c.get("image_uris", {}).get("normal", "")
                                if not img and "card_faces" in c:
                                    img = c["card_faces"][0].get("image_uris", {}).get("normal", "")
                                price_val = c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil") or "0.00"
                                card_info = {
                                    "name": c["name"],
                                    "image": img,
                                    "type": c.get("type_line", ""),
                                    "cmc": c.get("cmc", 0.0),
                                    "colors": c.get("colors", []),
                                    "color_identity": c.get("color_identity", []),
                                    "prices": c.get("prices", {}),
                                    "price": price_val,
                                    "legalities": c.get("legalities", {})
                                }
                                scryfall_cache.set(f"card:{orig_n_lower}", card_info)
                                scryfall_cache.set(f"card:{input_name_lower}", card_info)
                                scryfall_cache.set(f"card:{c['name'].lower().strip()}", card_info)
                                
                                scryfall_data[orig_n_lower] = card_info
                                scryfall_data[input_name_lower] = card_info
                                scryfall_data[c["name"].lower().strip()] = card_info
                                if "//" in c["name"]:
                                    front_face = c["name"].split("//")[0].strip().lower()
                                    scryfall_cache.set(f"card:{front_face}", card_info)
                                    scryfall_data[front_face] = card_info
                                continue
                        except Exception:
                            pass
                            
                        # Fallback 2: Search across all languages (great for German names)
                        try:
                            url_search = f"https://api.scryfall.com/cards/search?q=lang:any+name:%22{urllib.parse.quote(input_name)}%22"
                            resp_s = await client.get(url_search)
                            if resp_s.status_code == 200:
                                search_data = resp_s.json()
                                if "data" in search_data and len(search_data["data"]) > 0:
                                    c = search_data["data"][0]
                                    img = c.get("image_uris", {}).get("normal", "")
                                    if not img and "card_faces" in c:
                                        img = c["card_faces"][0].get("image_uris", {}).get("normal", "")
                                    price_val = c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil") or "0.00"
                                    card_info = {
                                        "name": c["name"],
                                        "image": img,
                                        "type": c.get("type_line", ""),
                                        "cmc": c.get("cmc", 0.0),
                                        "colors": c.get("colors", []),
                                        "color_identity": c.get("color_identity", []),
                                        "prices": c.get("prices", {}),
                                        "price": price_val,
                                        "legalities": c.get("legalities", {})
                                    }
                                    scryfall_cache.set(f"card:{orig_n_lower}", card_info)
                                    scryfall_cache.set(f"card:{input_name_lower}", card_info)
                                    scryfall_cache.set(f"card:{c['name'].lower().strip()}", card_info)
                                    
                                    scryfall_data[orig_n_lower] = card_info
                                    scryfall_data[input_name_lower] = card_info
                                    scryfall_data[c["name"].lower().strip()] = card_info
                                    if "//" in c["name"]:
                                        front_face = c["name"].split("//")[0].strip().lower()
                                        scryfall_cache.set(f"card:{front_face}", card_info)
                                        scryfall_data[front_face] = card_info
                                    continue
                        except Exception:
                            pass
                            
    return scryfall_data

@app.get("/api/suche/{search_term}")
async def suche_karte(search_term: str, benutzername: str = ""):
    is_premium = await check_user_premium(benutzername)
    cache_key = f"suche:{search_term.lower().strip()}:{is_premium}"
    cached = scryfall_cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(search_term)}"
        resp = await client.get(url)
        
        # If named?fuzzy fails, try language-independent search as fallback
        if resp.status_code != 200:
            try:
                url_search = f"https://api.scryfall.com/cards/search?q=lang:any+name:%22{urllib.parse.quote(search_term)}%22"
                search_resp = await client.get(url_search)
                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    if "data" in search_data and len(search_data["data"]) > 0:
                        english_name = search_data["data"][0]["name"]
                        url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(english_name)}"
                        resp = await client.get(url)
            except Exception:
                pass

        if resp.status_code == 200:
            data = resp.json()
            bild = data.get("image_uris", {}).get("normal", "")
            if not bild and "card_faces" in data:
                bild = data["card_faces"][0].get("image_uris", {}).get("normal", "")
            
            # rules text extraction
            oracle_text = data.get("oracle_text", "")
            if not oracle_text and "card_faces" in data:
                oracle_text = "\n//\n".join([face.get("oracle_text", "") for face in data["card_faces"]])
            
            # rules text translation to German
            text_de = "Keine Textbeschreibung vorhanden."
            if oracle_text:
                if is_premium and model:
                    try:
                        prompt = f"Übersetze diesen Magic: The Gathering Kartentext möglichst akkurat ins Deutsche (benutze offizielle MTG-Terminologie wie 'Fliegend', 'Tappen', 'Verursacht Trampelschaden', 'Erzeuge', etc.). Antworte NUR mit dem übersetzten Text:\n{oracle_text}"
                        response = model.generate_content(prompt)
                        text_de = response.text.strip()
                    except Exception as e:
                        text_de = f"Originaltext (Englisch):\n{oracle_text}"
                else:
                    if not is_premium:
                        text_de = f"[Premium-Feature: Upgrade auf MTG Pro für deutsche Übersetzung]\n\nOriginaltext (Englisch):\n{oracle_text}"
                    else:
                        text_de = f"Originaltext (Englisch):\n{oracle_text}"
            
            # Fetch all prints of the card
            prints = []
            prints_url = data.get("prints_search_uri")
            if prints_url:
                try:
                    prints_resp = await client.get(prints_url)
                    if prints_resp.status_code == 200:
                        prints_data = prints_resp.json()
                        for item in prints_data.get("data", []):
                            img_print = item.get("image_uris", {}).get("normal", "")
                            if not img_print and "card_faces" in item:
                                img_print = item["card_faces"][0].get("image_uris", {}).get("normal", "")
                            
                            price_eur = item.get("prices", {}).get("eur") or item.get("prices", {}).get("eur_foil") or "0.00"
                            
                            prints.append({
                                "set_name": item.get("set_name"),
                                "bild_url": img_print,
                                "preis": price_eur
                            })
                except Exception as e:
                    print(f"Error fetching prints: {e}")
            
            if not prints:
                prints = [{
                    "set_name": data.get("set_name"),
                    "bild_url": bild,
                    "preis": data.get("prices", {}).get("eur", "0.00")
                }]
            
            result = {
                "name": data.get("name"),
                "typ": data.get("type_line"),
                "text_de": text_de,
                "prints": prints
            }
            scryfall_cache.set(cache_key, result)
            
            # Cache individual card info as well
            card_info = {
                "name": data.get("name"),
                "image": bild,
                "type": data.get("type_line", ""),
                "cmc": data.get("cmc", 0.0),
                "colors": data.get("colors", []),
                "color_identity": data.get("color_identity", []),
                "prices": data.get("prices", {}),
                "price": data.get("prices", {}).get("eur", "0.00"),
                "legalities": data.get("legalities", {})
            }
            scryfall_cache.set(f"card:{data.get('name').lower().strip()}", card_info)
            
            return result
        return {"error": "Karte nicht gefunden"}

# ==========================================
# 3. SAMMLUNG & ALBEN
# ==========================================
@app.get("/api/sammlung/{benutzername}")
async def get_sammlung(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
            {"name": benutzername}
        )
        rows = res.mappings().all()
        
        unique_names = list(set(row["karten_name"] for row in rows if row["karten_name"] != "__PLACEHOLDER__"))
        scryfall_data = await fetch_card_details_cached(unique_names)
        
        alben = {}
        for row in rows:
            album = row["album_name"]
            if album not in alben: alben[album] = []
            
            karten_name = row["karten_name"]
            card_info = scryfall_data.get(karten_name.lower().strip())
            
            live_preis = card_info.get("price", row["preis"]) if card_info else row["preis"]
            live_bild = card_info.get("image", row["bild_url"]) if card_info else row["bild_url"]
            
            alben[album].append({
                "id": row["id"],
                "name": karten_name,
                "bild_url": live_bild,
                "preis": row["preis"],
                "livePreis": live_preis
            })
        return {"erfolg": True, "alben": alben}

class AddKarteData(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str
    bild_url: str = ""
    preis: str = "0.00"

@app.post("/api/sammlung/hinzufuegen")
async def add_karte(data: AddKarteData):
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) VALUES (:user, :name, :album, :url, :price)"),
            {"user": data.benutzername, "name": data.karten_name, "album": data.album_name, "url": data.bild_url, "price": data.preis}
        )
    return {"erfolg": True}

class DeleteKarteData(BaseModel):
    karten_id: int

@app.post("/api/sammlung/loeschen")
async def delete_karte(data: DeleteKarteData):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE id = :id"),
            {"id": data.karten_id}
        )
    return {"erfolg": True}

class DeleteAlbumData(BaseModel):
    benutzername: str
    album_name: str

@app.post("/api/sammlung/album_loeschen")
async def delete_album(data: DeleteAlbumData):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE benutzername = :user AND album_name = :album"),
            {"user": data.benutzername, "album": data.album_name}
        )
    return {"erfolg": True}

# ==========================================
# 4. DECKS VERWALTUNG & FUNKTIONEN
# ==========================================
@app.get("/api/decks/{benutzername}")
async def get_decks(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM decks WHERE benutzername = :name"),
            {"name": benutzername}
        )
        rows = res.mappings().all()
        return [{"id": r["id"], "name": r["deck_name"], "liste": r["deck_liste"]} for r in rows]

class CreateDeckData(BaseModel):
    benutzername: str
    deck_name: str
    deck_liste: str

@app.post("/api/decks/erstellen")
async def create_deck(data: CreateDeckData):
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO decks (benutzername, deck_name, deck_liste) VALUES (:user, :name, :list)"),
            {"user": data.benutzername, "name": data.deck_name, "list": data.deck_liste}
        )
    return {"erfolg": True}

class UpdateDeckData(BaseModel):
    deck_id: int
    deck_liste: str

@app.post("/api/decks/update")
async def update_deck(data: UpdateDeckData):
    async with get_db_session() as session:
        await session.execute(
            text("UPDATE decks SET deck_liste = :list WHERE id = :id"),
            {"list": data.deck_liste, "id": data.deck_id}
        )
    return {"erfolg": True}

class DeleteDeckReq(BaseModel):
    deck_id: int
    benutzername: str

@app.post("/api/decks/loeschen")
async def delete_deck(data: DeleteDeckReq):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM decks WHERE id = :id AND benutzername = :user"),
            {"id": data.deck_id, "user": data.benutzername}
        )
    return {"erfolg": True}

class DeckAnalyseReq(BaseModel):
    deck_liste: str

def clean_card_name(name: str) -> str:
    # Remove foil tags
    name = re.sub(r'\*[fF](oil)?\*', '', name)
    name = re.sub(r'(?i)\bfoil\b', '', name)
    
    # Strip any ending parentheses or brackets with text inside (e.g. (Commander), (Nicht gefunden), [Showcase])
    while True:
        new_name = re.sub(r'\s*\([^)]+\)\s*$', '', name)
        new_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', new_name)
        if new_name == name:
            break
        name = new_name
        
    # Standard set codes / collector numbers like (ELD) 123
    name = re.sub(r'\([a-zA-Z0-9]{3,4}\)\s*\d*', '', name)
    name = re.sub(r'\([a-zA-Z0-9]{3,4}\)', '', name)
    name = re.sub(r'\[[a-zA-Z0-9]{3,4}\]\s*\d*', '', name)
    name = re.sub(r'\[[a-zA-Z0-9]{3,4}\]', '', name)
    
    # Trailing digits
    name = re.sub(r'\s+\d+$', '', name)
    
    # Split by // to handle double-faced/split cards and take the front face
    if "//" in name:
        name = name.split("//")[0].strip()
        
    return re.sub(r'\s+', ' ', name).strip()

# Helfer zum Auslesen von Decklisten ("1x Sol Ring")
def parse_decklist(deck_liste: str):
    lines = deck_liste.strip().split('\n')
    parsed = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('#') or line.startswith('//') or line.lower().endswith(':'):
            continue
        match = re.match(r'^(\d+)[xX]?\s+(.+)$', line)
        if match:
            parsed.append({"count": int(match.group(1)), "name": clean_card_name(match.group(2).strip())})
        else:
            parsed.append({"count": 1, "name": clean_card_name(line)})
    return parsed

@app.post("/api/deck/visualize")
async def deck_visualize(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    if not parsed: return {"karten": []}
    
    unique_names = list(set([p["name"] for p in parsed]))
    scryfall_data = await fetch_card_details_cached(unique_names)
                    
    karten = []
    for p in parsed:
        name_lower = p["name"].lower().strip()
        if name_lower in scryfall_data:
            karten.append({
                "count": p["count"],
                "name": scryfall_data[name_lower]["name"],
                "image": scryfall_data[name_lower]["image"],
                "type": scryfall_data[name_lower]["type"]
            })
        else:
            karten.append({
                "count": p["count"],
                "name": p["name"] + " (Nicht gefunden)",
                "image": "",
                "type": "Unbekannt"
            })
            
    return {"karten": karten}

@app.post("/api/deck/stats")
async def deck_stats(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    unique_names = list(set([p["name"] for p in parsed]))
    cmc_counts = {}
    color_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
    
    scryfall_data = await fetch_card_details_cached(unique_names)
    for p in parsed:
        name_lower = p["name"].lower().strip()
        c = scryfall_data.get(name_lower)
        if not c:
            continue
        count = p["count"]
        
        try:
            cmc = int(float(c.get("cmc") or 0.0))
        except (ValueError, TypeError):
            cmc = 0
        if "Land" not in c.get("type", ""):
            cmc_counts[str(cmc)] = cmc_counts.get(str(cmc), 0) + count
            
        colors = c.get("colors", [])
        if not colors:
            if "Land" not in c.get("type", ""):
                color_counts["C"] += count
        else:
            for color in set(colors):
                if color in color_counts:
                    color_counts[color] += count
                                
    return {"cmc": cmc_counts, "colors": color_counts}

@app.post("/api/deck/wert")
async def deck_wert(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    unique_names = list(set([p["name"] for p in parsed]))
    total_value = 0.0
    
    scryfall_data = await fetch_card_details_cached(unique_names)
    for p in parsed:
        name_lower = p["name"].lower().strip()
        c = scryfall_data.get(name_lower)
        if not c:
            continue
        count = p["count"]
        try:
            price = float(c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil") or 0.0)
        except (ValueError, TypeError):
            price = 0.0
        total_value += (price * count)
                    
    return {"gesamt_wert": f"{total_value:.2f}"}

async def check_user_premium(benutzername: str) -> bool:
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
    except Exception as e:
        print(f"Error checking user role: {e}")
    return False

class DeckAnalyseReq(BaseModel):
    deck_liste: str
    benutzername: str = ""
    format: str = "commander"

@app.post("/api/deck/analyse")
async def deck_analyse(req: DeckAnalyseReq):
    is_premium = await check_user_premium(req.benutzername)
    if not is_premium:
        return {"error": "paywall", "message": "Dieses Premium-Feature (KI-Deck-Analyse) steht nur Premium-Mitgliedern zur Verfügung."}
        
    if model:
        try:
            prompt = (
                f"Analysiere dieses Magic the Gathering Deck auf Deutsch unter Berücksichtigung des Formats: '{req.format}'.\n"
                f"Format-Spezifikationen:\n"
                f"- Commander: Multiplayer, Singleton, Turn 8-12 durchschnittlich, Synergien mit Commander entscheidend.\n"
                f"- Standard: Best-of-3, 60 Karten, Turn 5-8, Konstanz und 4-of-Kopien wichtig.\n"
                f"- Modern: Turn 3-5, hoch-interaktiv, starke Interaktion & Antworten erforderlich.\n"
                f"- Legacy: Turn 1-3, Combo-lastig, extrem hohe Effizienz.\n"
                f"- Vintage: Restricted Cards, Power 9 erlaubt, maximale Turn 1-2 Explosivität.\n\n"
                f"Gib die Antwort EXAKT als JSON (ohne Markdown Code Block) mit den folgenden Schlüsseln zurück:\n"
                f"- 'strategie' (string)\n"
                f"- 'commander' (string, falls vorhanden, sonst 'Das Deck')\n"
                f"- 'staerken' (array of strings)\n"
                f"- 'schwaechen' (object mit Schlüsseln: 'card_draw', 'removal', 'ramp', 'protection', 'winconditions', wobei jeder Schlüssel ein-Objekt mit 'score' (int, 1-10) und 'text' (string) ist)\n"
                f"- 'synergien' (array of objects mit Schlüsseln: 'karten' (array of strings) und 'erklaerung' (string))\n"
                f"- 'combos' (array of objects mit Schlüsseln: 'karten' (array of strings), 'typ' (string, z.B. 'Infinite Token', 'Infinite Mana') und 'erklaerung' (string))\n"
                f"- 'verbesserungen' (array of objects mit Schlüsseln: 'rein' (string), 'raus' (string oder null), 'grund' (string))\n"
                f"- 'format_kontext' (string)\n"
                f"- 'power_level' (int, 1-10)\n\n"
                f"Deckliste:\n{req.deck_liste}"
            )
            response = model.generate_content(prompt)
            text = response.text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                text = match.group(0)
            return json.loads(text)
        except Exception as e:
            print(f"Error generating deck analysis: {e}")
            pass
            
    return {
        "strategie": "Konnte durch die KI aktuell nicht ausgewertet werden.",
        "commander": "Unbekannt",
        "staerken": ["API oder KI Model offline"],
        "schwaechen": {
            "card_draw": {"score": 5, "text": "Keine card draw Daten verfügbar."},
            "removal": {"score": 5, "text": "Keine removal Daten verfügbar."},
            "ramp": {"score": 5, "text": "Keine ramp Daten verfügbar."},
            "protection": {"score": 5, "text": "Keine protection Daten verfügbar."},
            "winconditions": {"score": 5, "text": "Keine winconditions Daten verfügbar."}
        },
        "synergien": [],
        "combos": [],
        "verbesserungen": [],
        "format_kontext": "Format-Kontext konnte nicht bestimmt werden.",
        "power_level": 5
    }

# ==========================================
# 5. KI & ZUSATZFUNKTIONEN (PREMIUM GESCHÜTZT)
# ==========================================
class JudgeRequest(BaseModel):
    frage: str
    benutzername: str = ""

@app.post("/api/judge")
async def judge_endpoint(req: JudgeRequest):
    is_premium = await check_user_premium(req.benutzername)
    if not is_premium:
        return {"antwort": "PAYWALL: Der KI-Judge steht nur Premium-Mitgliedern zur Verfügung. Bitte upgrade deine Rolle im Premium-Tab!"}
        
    if model:
        try:
            response = model.generate_content(f"Beantworte diese Magic The Gathering Regelfrage kurz auf Deutsch: {req.frage}")
            return {"antwort": response.text}
        except:
            pass
    return {"antwort": "Der KI-Judge ist momentan beschäftigt oder nicht eingerichtet. Bitte überprüfe deinen API Key."}

@app.get("/api/combos/{card_name}")
async def get_combos(card_name: str, benutzername: str = ""):
    is_premium = await check_user_premium(benutzername)
    if not is_premium:
        return {"error": "paywall", "empfehlungen": [], "message": "Der KI-Synergie-Scanner steht nur Premium-Mitgliedern zur Verfügung."}
        
    if model:
        try:
            prompt = f"Finde bekannte Magic The Gathering Kombinationen (Combos) für die Karte '{card_name}'. Antworte auf Deutsch und gib das Ergebnis EXAKT als JSON mit dem Schlüssel 'empfehlungen' (eine Liste von Objekten, jedes mit 'name' (z.B. Card1 + Card2) und 'grund' (Erklärung)) zurück (ohne Markdown Code Block)."
            response = model.generate_content(prompt)
            text = response.text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                text = match.group(0)
            return json.loads(text)
        except Exception as e:
            print(f"Error fetching combos: {e}")
            pass
    return {"empfehlungen": [
        {"name": f"{card_name} + Sol Ring", "grund": "Generischer Mana-Boost für schnellere Aktivierung der Karte."},
        {"name": f"{card_name} + Command Tower", "grund": "Perfekte Farbstabilität in Mehrfarbendecks."}
    ]}

class ScanCombosReq(BaseModel):
    karten_liste: str
    benutzername: str = ""

@app.post("/api/scan_combos")
async def scan_combos(req: ScanCombosReq):
    is_premium = await check_user_premium(req.benutzername)
    if not is_premium:
        return {"error": "paywall", "combos": [], "message": "Der KI-Synergie-Scanner steht nur Premium-Mitgliedern zur Verfügung."}
        
    if model:
        try:
            prompt = f"Analysiere diese Liste von Magic The Gathering Karten und finde bekannte Kombinationen (Combos) oder starke Synergien zwischen ihnen. Gib das Ergebnis auf Deutsch EXAKT als JSON mit dem Schlüssel 'combos' (eine Liste von Objekten, jedes mit 'name' (Kartenname + Kartenname) und 'grund' (kurze Erklärung)) zurück (ohne Markdown Code Block). Kartenliste:\n{req.karten_liste}"
            response = model.generate_content(prompt)
            text = response.text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                text = match.group(0)
            return json.loads(text)
        except Exception as e:
            print(f"Error scanning combos: {e}")
            pass
    return {"combos": []}

# ==========================================
# 6. DECK VALIDATION (LEVEL 3 JUDGE RULES)
# ==========================================
class ValidateDeckReq(BaseModel):
    deck_liste: str
    format: str = "commander"

from format_engine import FormatValidator

@app.post("/api/deck/validate")
async def validate_deck(req: ValidateDeckReq):
    try:
        result = await FormatValidator.validate_deck(req.deck_liste, req.format, fetch_card_details_cached)
        return result
    except Exception as e:
        print(f"Error in validate_deck: {e}")
        return {
            "legal": False,
            "errors": [f"Fehler bei der Deck-Validierung: {str(e)}"],
            "warnings": [],
            "details": {"format": req.format, "total_cards": 0}
        }

# ==========================================
# 7. STRIPE INTEGRATION & PRICING
# ==========================================
class CheckoutReq(BaseModel):
    benutzername: str
    host_url: str = "http://localhost:5173"

@app.post("/api/checkout/create-session")
async def create_checkout_session(req: CheckoutReq):
    if not req.benutzername:
        return {"erfolg": False, "error": "Benutzername erforderlich"}
    
    stripe_key = os.getenv("STRIPE_API_KEY")
    if not stripe_key:
        # Fallback simulated checkout url
        mock_success_url = f"{req.host_url}/premium?status=success&mock_upgrade=true&user={urllib.parse.quote(req.benutzername)}"
        return {"erfolg": True, "url": mock_success_url, "simulated": True}
        
    try:
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price': os.getenv("STRIPE_PRICE_ID", "price_dummy_123"),
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=req.host_url + "/premium?status=success&session_id={CHECKOUT_SESSION_ID}&user=" + urllib.parse.quote(req.benutzername),
            cancel_url=req.host_url + "/premium?status=cancel",
            metadata={
                "benutzername": req.benutzername
            }
        )
        return {"erfolg": True, "url": session.url, "simulated": False}
    except Exception as e:
        return {"erfolg": False, "error": str(e)}

def get_stripe_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)

@app.post("/api/checkout/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    event = None
    try:
        if webhook_secret and sig_header:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            data = json.loads(payload)
            event = stripe.Event.construct_from(data, stripe.api_key)
    except Exception as e:
        print(f"GLOBALER FEHLER: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})
        
    if event:
        event_type = get_stripe_val(event, "type")
        event_data = get_stripe_val(event, "data", {})
        event_obj = get_stripe_val(event_data, "object")
        
        if event_type == "checkout.session.completed":
            metadata = get_stripe_val(event_obj, "metadata", {})
            benutzername = get_stripe_val(metadata, "benutzername")
            customer_id = get_stripe_val(event_obj, "customer")
            if benutzername:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='premium', stripe_customer_id = :cust_id WHERE benutzername = :name"),
                        {"cust_id": customer_id, "name": benutzername}
                    )
                print(f"User {benutzername} upgraded to premium via Stripe with Customer ID {customer_id}.")
                return {"status": "success", "message": f"User {benutzername} upgraded to premium"}
                
        elif event_type == "customer.subscription.deleted":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free' WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                print(f"Downgraded user with Stripe Customer ID {customer_id} to free.")
                return {"status": "success", "message": "User subscription cancelled"}
                
        elif event_type == "invoice.payment_failed":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free' WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                print(f"Downgraded user with Stripe Customer ID {customer_id} due to payment failure.")
                return {"status": "success", "message": "User subscription suspended"}
            
    return {"status": "ignored"}

class UpgradeReq(BaseModel):
    benutzername: str
    rolle: str = "premium"

@app.post("/api/user/update-role")
async def update_user_role(req: UpgradeReq):
    async with get_db_session() as session:
        await session.execute(
            text("UPDATE nutzer SET rolle = :role WHERE benutzername = :name"),
            {"role": req.rolle, "name": req.benutzername}
        )
    return {"erfolg": True, "rolle": req.rolle}

# ==========================================
# 8. PHASE B – ERWEITERTE SAMMLUNG & DECK ENDPOINTS
# ==========================================

# --- 8.1 Sammlung Filter ---
@app.get("/api/sammlung/{benutzername}/filter")
async def sammlung_filter(
    benutzername: str,
    farbe: str = Query(default=None, description="Farbe (W, U, B, R, G)"),
    seltenheit: str = Query(default=None, description="Seltenheit (common, uncommon, rare, mythic)"),
    edition: str = Query(default=None, description="Edition / Set-Code"),
    manakosten_min: int = Query(default=None, description="Minimale Manakosten (CMC)"),
    manakosten_max: int = Query(default=None, description="Maximale Manakosten (CMC)"),
    typ: str = Query(default=None, description="Kartentyp (Creature, Instant, Sorcery, ...)"),
    suche: str = Query(default=None, description="Freitextsuche im Kartennamen"),
    album: str = Query(default=None, description="Filter nach Albumname")
):
    """Filtert die Sammlung eines Benutzers anhand von Scryfall-Metadaten."""
    try:
        async with get_db_session() as session:
            if album:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name = :album"),
                    {"name": benutzername, "album": album}
                )
            else:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name != 'Wunschliste'"),
                    {"name": benutzername}
                )
            rows = res.mappings().all()

        if not rows:
            return {"erfolg": True, "karten": []}

        # Collect unique card names and fetch Scryfall data
        unique_names = list(set(row["karten_name"] for row in rows))
        scryfall_data = await fetch_card_details_cached(unique_names)

        result = []
        for row in rows:
            name_lower = row["karten_name"].lower().strip()
            card_info = scryfall_data.get(name_lower)
            if not card_info:
                continue

            # --- Apply filters ---
            # Freitextsuche im Namen
            if suche and suche.lower() not in card_info.get("name", "").lower():
                continue

            # Farbfilter
            if farbe:
                card_colors = card_info.get("colors", []) or card_info.get("color_identity", [])
                if farbe.upper() not in [c.upper() for c in card_colors]:
                    continue

            # Seltenheit
            if seltenheit:
                card_rarity = card_info.get("rarity", "").lower()
                if card_rarity != seltenheit.lower():
                    continue

            # Edition / Set
            if edition:
                card_set = card_info.get("set", "").lower()
                if card_set != edition.lower():
                    continue

            # Manakosten min/max
            try:
                card_cmc = float(card_info.get("cmc", 0))
            except (ValueError, TypeError):
                card_cmc = 0.0
            if manakosten_min is not None and card_cmc < manakosten_min:
                continue
            if manakosten_max is not None and card_cmc > manakosten_max:
                continue

            # Typfilter
            if typ:
                card_type = card_info.get("type", "").lower()
                if typ.lower() not in card_type:
                    continue

            result.append({
                "id": row["id"],
                "name": card_info.get("name", row["karten_name"]),
                "type": card_info.get("type", ""),
                "colors": card_info.get("colors", []),
                "cmc": card_info.get("cmc", 0),
                "rarity": card_info.get("rarity", ""),
                "set": card_info.get("set", ""),
                "image_url": card_info.get("image", row["bild_url"]),
                "price": card_info.get("price", row["preis"]),
                "album_name": row["album_name"]
            })

        return {"erfolg": True, "karten": result}
    except Exception as e:
        print(f"Fehler bei Sammlung-Filter: {e}")
        return {"erfolg": False, "error": str(e)}


# --- 8.2 Editionen (distinct sets in user's collection) ---
@app.get("/api/sammlung/{benutzername}/editions")
async def sammlung_editions(benutzername: str):
    """Gibt die einzigartigen Editionen aus der Sammlung eines Benutzers zurück."""
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name"),
                {"name": benutzername}
            )
            rows = res.mappings().all()

        if not rows:
            return {"erfolg": True, "editions": []}

        unique_names = [row["karten_name"] for row in rows]
        scryfall_data = await fetch_card_details_cached(unique_names)

        editions_seen = set()
        editions = []
        for card_info in scryfall_data.values():
            set_code = card_info.get("set", "")
            set_name = card_info.get("set_name", set_code)
            if set_code and set_code not in editions_seen:
                editions_seen.add(set_code)
                editions.append({"set_code": set_code, "set_name": set_name})

        editions.sort(key=lambda e: e["set_name"])
        return {"erfolg": True, "editions": editions}
    except Exception as e:
        print(f"Fehler bei Editionen-Abfrage: {e}")
        return {"erfolg": False, "error": str(e)}


# --- 8.3 CSV Import ---
@app.post("/api/sammlung/import-csv")
async def sammlung_import_csv(
    file: UploadFile = File(...),
    benutzername: str = Form(...),
    album_name: str = Form("Import")
):
    """Importiert Karten aus einer CSV-Datei in die Sammlung.
    CSV-Format: Kartenname,Anzahl,Edition,Album
    """
    try:
        content = await file.read()
        csv_text = content.decode("utf-8-sig")  # handles BOM from Excel
        reader = csv.reader(io.StringIO(csv_text))

        imported = 0
        failed = 0
        errors_list = []
        rows_to_insert = []

        for row_num, row in enumerate(reader, start=1):
            # Skip empty rows and header row
            if not row or (row_num == 1 and row[0].strip().lower() in ["kartenname", "name", "card"]):
                continue

            karten_name = row[0].strip() if len(row) > 0 else ""
            try:
                anzahl = int(row[1].strip()) if len(row) > 1 and row[1].strip() else 1
            except ValueError:
                anzahl = 1
            csv_edition = row[2].strip() if len(row) > 2 else ""
            csv_album = row[3].strip() if len(row) > 3 else album_name

            if not karten_name:
                failed += 1
                errors_list.append(f"Zeile {row_num}: Leerer Kartenname.")
                continue

            # Validate card via Scryfall
            scryfall_data = await fetch_card_details_cached([karten_name])
            name_lower = karten_name.lower().strip()
            card_info = scryfall_data.get(name_lower)

            if not card_info:
                failed += 1
                errors_list.append(f"Zeile {row_num}: Karte '{karten_name}' nicht in Scryfall gefunden.")
                continue

            # Use Scryfall canonical name, image, and price
            canonical_name = card_info.get("name", karten_name)
            bild_url = card_info.get("image", "")
            price_val = card_info.get("price", "0.00")

            for _ in range(anzahl):
                rows_to_insert.append(
                    (benutzername, canonical_name, csv_album or album_name, bild_url, str(price_val))
                )
            imported += anzahl

        # Bulk insert
        if rows_to_insert:
            async with get_db_session() as session:
                await session.execute(
                    text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) VALUES (:user, :name, :album, :url, :price)"),
                    [{"user": r[0], "name": r[1], "album": r[2], "url": r[3], "price": r[4]} for r in rows_to_insert]
                )

        return {"erfolg": True, "imported": imported, "failed": failed, "errors": errors_list}
    except Exception as e:
        print(f"Fehler beim CSV-Import: {e}")
        return {"erfolg": False, "imported": 0, "failed": 0, "error": str(e)}


# --- 8.4 CSV Export ---
@app.get("/api/sammlung/{benutzername}/export-csv")
async def sammlung_export_csv(benutzername: str):
    """Exportiert die gesamte Sammlung eines Benutzers als CSV-Datei."""
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
                {"name": benutzername}
            )
            rows = res.mappings().all()

        # Aggregate cards: group by (karten_name, album_name) to get Anzahl
        aggregated = {}
        for row in rows:
            key = (row["karten_name"], row["album_name"])
            if key not in aggregated:
                aggregated[key] = {"anzahl": 0, "preis": row["preis"]}
            aggregated[key]["anzahl"] += 1

        # Fetch Scryfall data for set & price info
        unique_names = list(set(k[0] for k in aggregated.keys()))
        scryfall_data = await fetch_card_details_cached(unique_names) if unique_names else {}

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Kartenname", "Anzahl", "Edition", "Album", "Preis_EUR"])

        for (karten_name, album_name), info in sorted(aggregated.items()):
            name_lower = karten_name.lower().strip()
            card_info = scryfall_data.get(name_lower, {})
            edition_code = card_info.get("set", "")
            price_eur = card_info.get("price", info["preis"]) or info["preis"]
            writer.writerow([
                card_info.get("name", karten_name),
                info["anzahl"],
                edition_code,
                album_name,
                price_eur
            ])

        csv_content = output.getvalue()
        output.close()

        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8-sig")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="sammlung_{benutzername}.csv"'
            }
        )
    except Exception as e:
        print(f"Fehler beim CSV-Export: {e}")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})


# --- 8.5 Deck: Einzelne Karte hinzufügen ---
class DeckAddCardReq(BaseModel):
    deck_id: int
    card_name: str

@app.post("/api/deck/add-card")
async def deck_add_card(req: DeckAddCardReq):
    """Fügt eine Karte zum Deck hinzu oder erhöht deren Anzahl."""
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM decks WHERE id = :id"),
                {"id": req.deck_id}
            )
            deck = res.mappings().first()
            if not deck:
                return {"erfolg": False, "error": "Deck nicht gefunden."}

            deck_liste = deck["deck_liste"] or ""
            lines = deck_liste.strip().split('\n') if deck_liste.strip() else []

            # Check if card already exists in the list
            card_found = False
            updated_lines = []
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    updated_lines.append(line)
                    continue
                match = re.match(r'^(\d+)[xX]?\s+(.+)$', line_stripped)
                if match:
                    count = int(match.group(1))
                    name = match.group(2).strip()
                    if name.lower() == req.card_name.lower():
                        count += 1
                        card_found = True
                        updated_lines.append(f"{count} {name}")
                    else:
                        updated_lines.append(line)
                else:
                    # Lines without a count prefix
                    if line_stripped.lower() == req.card_name.lower():
                        card_found = True
                        updated_lines.append(f"2 {line_stripped}")
                    else:
                        updated_lines.append(line)

            if not card_found:
                updated_lines.append(f"1 {req.card_name}")

            new_liste = '\n'.join(updated_lines)
            await session.execute(
                text("UPDATE decks SET deck_liste = :list WHERE id = :id"),
                {"list": new_liste, "id": req.deck_id}
            )

        return {"erfolg": True, "deck_liste": new_liste}
    except Exception as e:
        print(f"Fehler beim Hinzufügen der Karte zum Deck: {e}")
        return {"erfolg": False, "error": str(e)}


# --- 8.6 Deck: Einzelne Karte entfernen ---
class DeckRemoveCardReq(BaseModel):
    deck_id: int
    card_name: str

@app.post("/api/deck/remove-card")
async def deck_remove_card(req: DeckRemoveCardReq):
    """Entfernt eine Karte aus dem Deck oder verringert deren Anzahl."""
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM decks WHERE id = :id"),
                {"id": req.deck_id}
            )
            deck = res.mappings().first()
            if not deck:
                return {"erfolg": False, "error": "Deck nicht gefunden."}

            deck_liste = deck["deck_liste"] or ""
            lines = deck_liste.strip().split('\n') if deck_liste.strip() else []

            card_found = False
            updated_lines = []
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    updated_lines.append(line)
                    continue
                match = re.match(r'^(\d+)[xX]?\s+(.+)$', line_stripped)
                if match:
                    count = int(match.group(1))
                    name = match.group(2).strip()
                    if name.lower() == req.card_name.lower():
                        card_found = True
                        count -= 1
                        if count > 0:
                            updated_lines.append(f"{count} {name}")
                    else:
                        updated_lines.append(line)
                else:
                    if line_stripped.lower() == req.card_name.lower():
                        card_found = True
                    else:
                        updated_lines.append(line)

            if not card_found:
                return {"erfolg": False, "error": f"Karte '{req.card_name}' nicht im Deck gefunden."}

            new_liste = '\n'.join(updated_lines)
            await session.execute(
                text("UPDATE decks SET deck_liste = :list WHERE id = :id"),
                {"list": new_liste, "id": req.deck_id}
            )

        return {"erfolg": True, "deck_liste": new_liste}
    except Exception as e:
        print(f"Fehler beim Entfernen der Karte aus dem Deck: {e}")
        return {"erfolg": False, "error": str(e)}

# ==========================================
# 8. OAUTH2 FLOWS (GOOGLE & DISCORD)
# ==========================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/api/auth/discord/callback")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

@app.get("/api/auth/google/login")
async def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured. Add GOOGLE_CLIENT_ID to .env")
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(GOOGLE_REDIRECT_URI)}&"
        f"scope=openid%20email%20profile&"
        f"response_type=code"
    )
    return RedirectResponse(url)

@app.get("/api/auth/google/callback")
async def google_callback(code: str):
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for access token
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve token from Google")
        token_data = resp.json()
        google_access_token = token_data.get("access_token")
        
        # 2. Get user info
        resp_user = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
            "Authorization": f"Bearer {google_access_token}"
        })
        if resp_user.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google")
        user_info = resp_user.json()
        email = user_info.get("email")
        name = user_info.get("name") or email.split("@")[0]
        google_id = user_info.get("sub")
        
        # Normalize username
        username = re.sub(r'[^a-zA-Z0-9_]', '', name.replace(" ", "_"))
        
        # 3. Create or login user in database
        async with get_db_session() as session:
            # Check if user already exists
            res = await session.execute(
                text("SELECT * FROM nutzer WHERE oauth_provider = 'google' AND oauth_id = :oid"),
                {"oid": google_id}
            )
            user_row = res.mappings().first()
            if not user_row:
                # Check username conflict
                res_u = await session.execute(
                    text("SELECT * FROM nutzer WHERE benutzername = :name"),
                    {"name": username}
                )
                if res_u.first():
                    username = f"{username}_{int(time.time()) % 1000}"
                    
                await session.execute(
                    text("INSERT INTO nutzer (benutzername, email, oauth_provider, oauth_id, rolle) VALUES (:name, :email, 'google', :oid, 'free')"),
                    {"name": username, "email": email, "oid": google_id}
                )
                role = "free"
            else:
                username = user_row["benutzername"]
                role = user_row["rolle"] or "free"
                
        # 4. Generate application JWT tokens
        jwt_token = create_access_token({"sub": username, "role": role})
        
        # Redirect to frontend with tokens
        redirect_url = f"{FRONTEND_URL}/?status=success&user={username}&token={jwt_token}&role={role}"
        return RedirectResponse(redirect_url)

@app.get("/api/auth/discord/login")
async def discord_login():
    if not DISCORD_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Discord OAuth is not configured. Add DISCORD_CLIENT_ID to .env")
    url = (
        f"https://discord.com/api/oauth2/authorize?"
        f"client_id={DISCORD_CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(DISCORD_REDIRECT_URI)}&"
        f"scope=identify%20email&"
        f"response_type=code"
    )
    return RedirectResponse(url)

@app.get("/api/auth/discord/callback")
async def discord_callback(code: str):
    async with httpx.AsyncClient() as client:
        # 1. Exchange code
        resp = await client.post("https://discord.com/api/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": DISCORD_REDIRECT_URI
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to retrieve token from Discord: {resp.text}")
        token_data = resp.json()
        discord_access_token = token_data.get("access_token")
        
        # 2. Get user info
        resp_user = await client.get("https://discord.com/api/users/@me", headers={
            "Authorization": f"Bearer {discord_access_token}"
        })
        if resp_user.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Discord")
        user_info = resp_user.json()
        email = user_info.get("email")
        name = user_info.get("username")
        discord_id = user_info.get("id")
        
        username = re.sub(r'[^a-zA-Z0-9_]', '', name)
        
        # 3. Save to DB
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM nutzer WHERE oauth_provider = 'discord' AND oauth_id = :oid"),
                {"oid": discord_id}
            )
            user_row = res.mappings().first()
            if not user_row:
                res_u = await session.execute(
                    text("SELECT * FROM nutzer WHERE benutzername = :name"),
                    {"name": username}
                )
                if res_u.first():
                    username = f"{username}_{int(time.time()) % 1000}"
                    
                await session.execute(
                    text("INSERT INTO nutzer (benutzername, email, oauth_provider, oauth_id, rolle) VALUES (:name, :email, 'discord', :oid, 'free')"),
                    {"name": username, "email": email, "oid": discord_id}
                )
                role = "free"
            else:
                username = user_row["benutzername"]
                role = user_row["rolle"] or "free"
                
        # 4. JWT Access Token
        jwt_token = create_access_token({"sub": username, "role": role})
        
        redirect_url = f"{FRONTEND_URL}/?status=success&user={username}&token={jwt_token}&role={role}"
        return RedirectResponse(redirect_url)