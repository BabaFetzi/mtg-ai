from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import urllib.parse
from google import genai
from google.genai import types
import json
import sqlite3
import hashlib
import re
import time
import os
from dotenv import load_dotenv

# --- UMWELTVARIABLEN LADEN ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# --- API CLIENT SICHER INITIALISIEREN ---
client = genai.Client(api_key=api_key)

HEADERS = {
    "User-Agent": "MTGAppPro/1.0", 
    "Accept": "application/json"
}

app = FastAPI(title="MTG App Pro Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean_json_response(text):
    text = text.strip()
    if text.startswith('```json'): text = text[7:]
    elif text.startswith('```'): text = text[3:]
    if text.endswith('```'): text = text[:-3]
    return text.strip()

def parse_decklist(deck_liste: str):
    karten_mengen = {}
    for zeile in deck_liste.split('\n'):
        zeile = zeile.strip()
        if not zeile: continue
        match = re.match(r'^(\d+)x?\s+(.*)$', zeile, re.IGNORECASE)
        if match:
            menge = int(match.group(1))
            name = match.group(2)
        else:
            menge = 1
            name = zeile
        name = re.sub(r'\s*[\(\[<].*$', '', name).strip()
        if name: karten_mengen[name] = karten_mengen.get(name, 0) + menge
    return karten_mengen

def init_db():
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS nutzer (benutzername TEXT PRIMARY KEY, passwort_hash TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS sammlung_alben (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, karten_name TEXT, album_name TEXT)')
    try: c.execute('ALTER TABLE sammlung_alben ADD COLUMN bild_url TEXT')
    except: pass
    try: c.execute('ALTER TABLE sammlung_alben ADD COLUMN preis TEXT')
    except: pass
    c.execute('CREATE TABLE IF NOT EXISTS decks (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, deck_name TEXT, deck_liste TEXT)')
    conn.commit()
    conn.close()

init_db()

def hash_passwort(passwort: str):
    return hashlib.sha256(passwort.encode()).hexdigest()

class NutzerAuth(BaseModel):
    benutzername: str
    passwort: str

class KarteSpeichern(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str
    bild_url: str
    preis: str 

class DeckRequest(BaseModel):
    benutzername: str
    deck_name: str
    deck_liste: str

class DeckUpdate(BaseModel):
    deck_id: int
    deck_liste: str

class DeckAnalyseRequest(BaseModel):
    deck_liste: str

class JudgeRequest(BaseModel):
    frage: str
    
class ComboScanRequest(BaseModel):
    karten_liste: str

@app.post("/api/register")
def register(user: NutzerAuth):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    try:
        c.execute('INSERT INTO nutzer (benutzername, passwort_hash) VALUES (?, ?)', (user.benutzername, hash_passwort(user.passwort)))
        conn.commit(); return {"erfolg": True}
    except: return {"erfolg": False, "error": "Dieser Benutzername ist bereits vergeben."}
    finally: conn.close()

@app.post("/api/login")
def login(user: NutzerAuth):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('SELECT * FROM nutzer WHERE benutzername=? AND passwort_hash=?', (user.benutzername, hash_passwort(user.passwort)))
    daten = c.fetchall(); conn.close()
    if len(daten) > 0: return {"erfolg": True}
    else: return {"erfolg": False, "error": "Falscher Benutzername oder Passwort."}

@app.post("/api/sammlung/hinzufuegen")
def karte_hinzufuegen(daten: KarteSpeichern):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) VALUES (?, ?, ?, ?, ?)', 
              (daten.benutzername, daten.karten_name, daten.album_name, daten.bild_url, daten.preis))
    conn.commit(); conn.close(); return {"erfolg": True}

@app.get("/api/sammlung/{benutzername}")
def hole_sammlung(benutzername: str):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    try: c.execute('SELECT id, karten_name, album_name, bild_url, preis FROM sammlung_alben WHERE benutzername=? ORDER BY album_name, karten_name', (benutzername,)); reihen = c.fetchall()
    except:
        c.execute('SELECT id, karten_name, album_name, bild_url FROM sammlung_alben WHERE benutzername=? ORDER BY album_name, karten_name', (benutzername,))
        reihen = [(r[0], r[1], r[2], r[3], "0.00") for r in c.fetchall()]
    conn.close()
    alben = {}
    for r in reihen:
        if r[2] not in alben: alben[r[2]] = []
        alben[r[2]].append({"id": r[0], "name": r[1], "bild_url": r[3] if r[3] else "https://via.placeholder.com/180", "preis": r[4] if r[4] else "0.00"})
    return {"erfolg": True, "alben": alben}

@app.post("/api/sammlung/loeschen")
def karte_loeschen(daten: dict):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('DELETE FROM sammlung_alben WHERE id=?', (daten.get("karten_id"),))
    conn.commit(); conn.close(); return {"erfolg": True}

@app.post("/api/sammlung/album_loeschen")
def album_loeschen(daten: dict):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('DELETE FROM sammlung_alben WHERE benutzername=? AND album_name=?', (daten.get("benutzername"), daten.get("album_name")))
    conn.commit(); conn.close(); return {"erfolg": True}

@app.post("/api/decks/erstellen")
def create_deck(d: DeckRequest):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('INSERT INTO decks (benutzername, deck_name, deck_liste) VALUES (?, ?, ?)', (d.benutzername, d.deck_name, d.deck_liste))
    conn.commit(); conn.close(); return {"erfolg": True}

@app.get("/api/decks/{user}")
def get_decks(user: str):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('SELECT id, deck_name, deck_liste FROM decks WHERE benutzername=?', (user,))
    rows = c.fetchall(); conn.close()
    return [{"id": r[0], "name": r[1], "liste": r[2]} for r in rows]

@app.post("/api/decks/update")
def update_deck(d: DeckUpdate):
    conn = sqlite3.connect('mtg_app.db'); c = conn.cursor()
    c.execute('UPDATE decks SET deck_liste=? WHERE id=?', (d.deck_liste, d.deck_id))
    conn.commit(); conn.close(); return {"erfolg": True}

# --- SUCH-LOGIK FÜR DEUTSCHE KARTEN PRIORISIERT ---
def scryfall_suche_kugelsicher(suchbegriff: str):
    suchbegriff = suchbegriff.strip()
    
    # Schutz vor Scryfall Rate-Limit: Strikte 100ms Pause (10 Requests/Sekunde max)
    time.sleep(0.1) 
    
    # 1. Zuerst exakt auf Englisch versuchen
    try:
        url_exact = f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(suchbegriff)}"
        res = requests.get(url_exact, headers=HEADERS)
        if res.status_code == 200: return res.json()
    except Exception as e: print(f"Error Exact: {e}")

    # 2. Direkte Text-Suche (Deutsch) - WICHTIG: KEINE Anführungszeichen um den Suchbegriff!
    try:
        search_query_de = f'{suchbegriff} lang:de'
        url_search_de = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote(search_query_de)}"
        res = requests.get(url_search_de, headers=HEADERS)
        if res.status_code == 200:
            daten = res.json().get("data", [])
            if daten: return daten[0]
    except Exception as e: print(f"Error lang:de: {e}")

    # 3. Text-Suche (Alle anderen Sprachen als Fallback)
    try:
        search_query_any = f'{suchbegriff} lang:any'
        url_search_any = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote(search_query_any)}"
        res = requests.get(url_search_any, headers=HEADERS)
        if res.status_code == 200:
            daten = res.json().get("data", [])
            if daten: return daten[0]
    except Exception as e: print(f"Error lang:any: {e}")
    
    # 4. Letzter Versuch: Fuzzy Search (Englisch mit leichten Tippfehlern)
    try:
        url_fuzzy = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(suchbegriff)}"
        res = requests.get(url_fuzzy, headers=HEADERS)
        if res.status_code == 200: return res.json()
    except Exception as e: print(f"Error Fuzzy: {e}")
    
    return None

def extrahiere_regeltext(daten):
    if not daten: return ""
    if "card_faces" in daten:
        gesichter_texte = [f"[{g.get('name', '')}]: {g.get('oracle_text', '')}" for g in daten["card_faces"]]
        if gesichter_texte: return " /// ".join(gesichter_texte)
    return daten.get("oracle_text", "")

@app.post("/api/deck/wert")
def berechne_deck_wert(anfrage: DeckAnalyseRequest):
    karten_mengen = parse_decklist(anfrage.deck_liste)
    if not karten_mengen: return {"gesamt_wert": "0.00"}

    gesamt_wert = 0.0
    for name, menge in list(karten_mengen.items())[:35]:
        daten = scryfall_suche_kugelsicher(name)
        if daten:
            preis_str = daten.get("prices", {}).get("eur")
            if preis_str is None:
                engl_name = daten.get("name")
                fallback_res = requests.get(f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(engl_name)}", headers=HEADERS)
                if fallback_res.status_code == 200: preis_str = fallback_res.json().get("prices", {}).get("eur")
            if preis_str:
                try: gesamt_wert += float(preis_str) * menge
                except: pass
    return {"gesamt_wert": f"{gesamt_wert:.2f}"}

@app.post("/api/deck/stats")
def berechne_deck_stats(anfrage: DeckAnalyseRequest):
    karten_mengen = parse_decklist(anfrage.deck_liste)
    if not karten_mengen: return {"cmc": {}, "colors": {}}

    cmc_verteilung = {}
    farb_verteilung = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
    
    for name, menge in list(karten_mengen.items())[:60]:
        daten = scryfall_suche_kugelsicher(name)
        if daten:
            type_line = daten.get("type_line", "")
            if "Land" not in type_line:
                cmc = int(float(daten.get("cmc", 0)))
                cmc_verteilung[cmc] = cmc_verteilung.get(cmc, 0) + menge
            
            colors = daten.get("colors", [])
            if not colors:
                if "Land" not in type_line: farb_verteilung["C"] += menge
            else:
                for c in colors:
                    if c in farb_verteilung: farb_verteilung[c] += menge
                    
    return {"cmc": cmc_verteilung, "colors": farb_verteilung}

@app.post("/api/deck/visualize")
def visualize_deck(anfrage: DeckAnalyseRequest):
    karten_mengen = parse_decklist(anfrage.deck_liste)
    if not karten_mengen: return {"karten": []}

    unique_names = list(karten_mengen.keys())
    visual_data = []

    for i in range(0, len(unique_names), 75):
        chunk = unique_names[i:i+75]
        identifiers = [{"name": n} for n in chunk if n] 
        processed_names = set()
        
        try:
            res = requests.post("https://api.scryfall.com/cards/collection", json={"identifiers": identifiers}, headers=HEADERS)
            if res.status_code == 200:
                data_json = res.json()
                
                for card in data_json.get("data", []):
                    bild = card.get("image_uris", {}).get("normal")
                    if not bild and "card_faces" in card:
                        bild = card["card_faces"][0].get("image_uris", {}).get("normal")
                    
                    req_name_matched = card["name"]
                    menge = 1
                    for req_name, req_count in karten_mengen.items():
                        if req_name.lower() in card["name"].lower():
                            req_name_matched = req_name
                            menge = req_count; break
                            
                    processed_names.add(req_name_matched)
                    visual_data.append({
                        "name": card["name"],
                        "count": menge,
                        "image": bild or "https://via.placeholder.com/240x340/2C2C2E/FFFFFF?text=Kein+Bild",
                        "type": card.get("type_line", "")
                    })
                    
                for nf in data_json.get("not_found", []):
                    nf_name = nf.get("name")
                    if not nf_name: continue
                    processed_names.add(nf_name)
                    
                    fb_card = scryfall_suche_kugelsicher(nf_name)
                    if fb_card:
                        bild = fb_card.get("image_uris", {}).get("normal")
                        if not bild and "card_faces" in fb_card:
                            bild = fb_card["card_faces"][0].get("image_uris", {}).get("normal")
                        visual_data.append({
                            "name": fb_card.get("name", nf_name),
                            "count": karten_mengen.get(nf_name, 1),
                            "image": bild or "https://via.placeholder.com/240x340/2C2C2E/FFFFFF?text=Kein+Bild",
                            "type": fb_card.get("type_line", "")
                        })
                    else:
                        short_name = nf_name[:20]
                        encoded_name = urllib.parse.quote(short_name)
                        visual_data.append({
                            "name": f"{nf_name} (Nicht gefunden)",
                            "count": karten_mengen.get(nf_name, 1),
                            "image": f"https://via.placeholder.com/240x340/FF3B30/FFFFFF?text={encoded_name}",
                            "type": "Unbekannt"
                        })
        except Exception as e: print("API Error:", e)
        
        for name in chunk:
            if name not in processed_names:
                fb_card = scryfall_suche_kugelsicher(name)
                if fb_card:
                    bild = fb_card.get("image_uris", {}).get("normal")
                    if not bild and "card_faces" in fb_card:
                        bild = fb_card["card_faces"][0].get("image_uris", {}).get("normal")
                    visual_data.append({
                        "name": fb_card.get("name", name),
                        "count": karten_mengen.get(name, 1),
                        "image": bild or "https://via.placeholder.com/240x340/2C2C2E/FFFFFF?text=Kein+Bild",
                        "type": fb_card.get("type_line", "")
                    })
                else:
                    short_name = name[:20]
                    encoded_name = urllib.parse.quote(short_name)
                    visual_data.append({
                        "name": f"{name} (Nicht gefunden)",
                        "count": karten_mengen.get(name, 1),
                        "image": f"https://via.placeholder.com/240x340/FF3B30/FFFFFF?text={encoded_name}",
                        "type": "Unbekannt"
                    })

    return {"karten": visual_data}

@app.get("/api/suche/{karten_name}")
def suche_karte(karten_name: str):
    base_data = scryfall_suche_kugelsicher(karten_name)
    if not base_data: return {"error": "Karte nicht gefunden"}
    exact_name = base_data.get("name")
    oracle_text = extrahiere_regeltext(base_data)
    
    prints_url = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote('!\"' + exact_name + '\" include:extras unique:prints')}"
    prints_res = requests.get(prints_url, headers=HEADERS)
    prints_data = []
    
    if prints_res.status_code == 200:
        for p in prints_res.json().get("data", [])[:15]: 
            bild = p.get("image_uris", {}).get("normal")
            if not bild and "card_faces" in p: bild = p["card_faces"][0].get("image_uris", {}).get("normal")
            preis = p.get("prices", {}).get("eur")
            if bild: prints_data.append({"set_name": p.get("set_name", "").upper(), "bild_url": bild, "preis": preis if preis else "0.00"})
                
    if not prints_data: 
        bild = base_data.get("image_uris", {}).get("normal")
        if not bild and "card_faces" in base_data: bild = base_data["card_faces"][0].get("image_uris", {}).get("normal")
        preis = base_data.get("prices", {}).get("eur")
        prints_data.append({"set_name": base_data.get("set_name", "").upper(), "bild_url": bild if bild else "https://via.placeholder.com/180", "preis": preis if preis else "0.00"})

    try:
        prompt = f"Übersetze den folgenden Magic Kartentext präzise ins Deutsche:\n\n{oracle_text}"
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
        text_de = res.text.strip()
    except: text_de = oracle_text 

    return {"name": exact_name, "typ": base_data.get("type_line"), "text_de": text_de, "prints": prints_data}

@app.get("/api/combos/{karten_name}")
def hole_combos(karten_name: str):
    daten = scryfall_suche_kugelsicher(karten_name)
    if not daten: return {"karten_name": karten_name, "empfehlungen": []}
    prompt = f"DU BIST MTG PROFI. Karte: {daten.get('name')}. Nenne exakt 3 extrem starke Combo-Karten dazu. Antworte AUSSCHLIESSLICH als JSON-Array: [ {{\"name\": \"...\", \"grund\": \"...\"}} ]"
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"))
        return {"karten_name": daten.get("name"), "empfehlungen": json.loads(clean_json_response(response.text))}
    except: return {"karten_name": daten.get("name"), "empfehlungen": []}

@app.post("/api/deck/analyse")
def analysiere_deck(anfrage: DeckAnalyseRequest):
    karten_mengen = parse_decklist(anfrage.deck_liste)
    if not karten_mengen: return {"error": "Deck ist leer oder Format wird nicht erkannt."}
            
    alle_fakten = ""
    for name in list(karten_mengen.keys())[:75]: 
        daten = scryfall_suche_kugelsicher(name)
        if daten: alle_fakten += f"KARTE: {daten.get('name')}\nTEXT: {extrahiere_regeltext(daten)}\n---\n"
    
    if not alle_fakten.strip():
        return {"error": "Keine gültigen Karten für die Analyse gefunden. Bitte überprüfe die Namen im Editor."}
            
    prompt = f"""DU BIST EIN MTG PROFI-JUDGE. Fakten der Sammlung: {alle_fakten}.
    Analysiere diese Liste akribisch auf starke 2- oder 3-Karten Combos und Synergien.
    Antworte ZWINGEND in folgendem JSON-Format:
    {{"commander": "...", "strategie": "...", "staerken": ["..."], "schwaechen": ["..."], "combos": [{{"karten": "Kartenname 1 + Kartenname 2", "erklaerung": "..."}}]}}"""
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"))
        return json.loads(clean_json_response(response.text))
    except Exception as e: 
        return {"error": "KI überlastet (Rate Limit). Bitte kurz warten."}

@app.post("/api/judge")
def mtg_judge(req: JudgeRequest):
    prompt = f"DU BIST EIN LEVEL 3 MTG JUDGE. Beantworte die folgende Regelfrage eines Spielers präzise, offiziell und auf Deutsch. Halte dich relativ kurz und erkläre die Interaktion verständlich.\nFrage: {req.frage}"
    try:
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
        return {"antwort": res.text}
    except: return {"antwort": "Verbindung zum Judge-Netzwerk abgebrochen. KI überlastet."}

@app.post("/api/scan_combos")
def scan_combos(anfrage: ComboScanRequest):
    zeilen = [z.strip() for z in anfrage.karten_liste.split('\n') if z.strip()]
    karten_liste_sicher = "\n".join(zeilen[:100]) 

    prompt = f"""DU BIST EIN MTG PROFI-JUDGE. Hier ist eine Liste von Magic-Karten aus der Sammlung eines Spielers:
    {karten_liste_sicher}
    
    Finde die 3 bis 7 stärksten Combos oder Synergien. Übersetze die Kartennamen zwingend auf die offiziellen ENGLISCHEN Namen.
    Antworte AUSSCHLIESSLICH im strikten JSON-Format als Array:
    [ {{"name": "Englischer Kartenname 1 + Englischer Kartenname 2", "grund": "Erklärung der Combo..."}} ]"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(temperature=0.1, response_mime_type="application/json")
        )
        return json.loads(clean_json_response(response.text))
    except Exception as e:
        return {"error": "KI Überlastet. Zu viele Anfragen in kurzer Zeit."}