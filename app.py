import requests
import streamlit as streamlit_app
from google import genai
from google.genai import types
import urllib.parse
import time
import sqlite3
import hashlib

# 1. Hier deinen echten, kostenlosen Gemini API Key eintragen!
client = genai.Client(api_key="")

# --- DATENBANK & SICHERHEIT ---
def erstelle_datenbank():
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS nutzer (benutzername TEXT PRIMARY KEY, passwort_hash TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS decks (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, deck_name TEXT, deck_liste TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS sammlung (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT, karten_name TEXT)')
    conn.commit()
    conn.close()

def hash_passwort(passwort):
    return hashlib.sha256(str.encode(passwort)).hexdigest()

def registriere_nutzer(benutzername, passwort):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO nutzer (benutzername, passwort_hash) VALUES (?, ?)', (benutzername, hash_passwort(passwort)))
        conn.commit()
        erfolg = True
    except sqlite3.IntegrityError:
        erfolg = False
    conn.close()
    return erfolg

def login_nutzer(benutzername, passwort):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('SELECT * FROM nutzer WHERE benutzername=? AND passwort_hash=?', (benutzername, hash_passwort(passwort)))
    daten = c.fetchall()
    conn.close()
    return len(daten) > 0

def speichere_deck(benutzername, deck_name, deck_liste):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('INSERT INTO decks (benutzername, deck_name, deck_liste) VALUES (?, ?, ?)', (benutzername, deck_name, deck_liste))
    conn.commit()
    conn.close()

def lade_decks(benutzername):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('SELECT id, deck_name, deck_liste FROM decks WHERE benutzername=?', (benutzername,))
    daten = c.fetchall()
    conn.close()
    return daten

def loesche_deck(deck_id):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('DELETE FROM decks WHERE id=?', (deck_id,))
    conn.commit()
    conn.close()

def speichere_karte(benutzername, karten_name):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('INSERT INTO sammlung (benutzername, karten_name) VALUES (?, ?)', (benutzername, karten_name))
    conn.commit()
    conn.close()

def lade_sammlung(benutzername):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('SELECT id, karten_name FROM sammlung WHERE benutzername=?', (benutzername,))
    daten = c.fetchall()
    conn.close()
    return daten

def loesche_karte(karten_id):
    conn = sqlite3.connect('mtg_app.db')
    c = conn.cursor()
    c.execute('DELETE FROM sammlung WHERE id=?', (karten_id,))
    conn.commit()
    conn.close()

erstelle_datenbank()


# --- MTG KI FUNKTIONEN ---
@streamlit_app.cache_data(show_spinner=False)
def hole_karten_daten(karten_name):
    karten_name_bereinigt = urllib.parse.quote(karten_name)
    url = f"https://api.scryfall.com/cards/named?fuzzy={karten_name_bereinigt}"
    antwort = requests.get(url)
    if antwort.status_code == 200:
        return antwort.json()
    return None

def extrahiere_regeltext(daten):
    if not daten: return "Keine Daten gefunden."
    if "card_faces" in daten:
        gesichter_texte = []
        for gesicht in daten["card_faces"]:
            name = gesicht.get("name", "Unbekannt")
            text = gesicht.get("oracle_text", "")
            if text: gesichter_texte.append(f"[{name}]: {text}")
        if gesichter_texte: return " /// ".join(gesichter_texte)
    return daten.get("oracle_text", "Kein Regeltext vorhanden.")

def suche_echte_combos(karten_liste):
    gefundene_combos = []
    reine_namen = []
    for zeile in karten_liste.split('\n'):
        zeile = zeile.strip()
        if not zeile: continue
        teile = zeile.split(' ', 1)
        if teile[0].isdigit() and len(teile) > 1:
            reine_namen.append(teile[1].lower())
        else:
            reine_namen.append(zeile.lower())
    try:
        url = "https://backend.commanderspellbook.com/api/combos/"
        antwort = requests.get(url)
        if antwort.status_code == 200:
            alle_combos = antwort.json().get('results', [])
            for combo in alle_combos:
                combo_karten = [k.get('name').lower() for k in combo.get('cards', [])]
                if combo_karten and all(karte in reine_namen for karte in combo_karten):
                    gefundene_combos.append({
                        "name": " + ".join([k.get('name') for k in combo.get('cards', [])]),
                        "ergebnis": combo.get('description', 'Keine Beschreibung vorhanden.')
                    })
    except Exception:
        pass
    return gefundene_combos

def hole_alle_karten_texte(deck_liste):
    gesammelte_texte = ""
    for zeile in deck_liste.split('\n'):
        zeile = zeile.strip()
        if not zeile: continue
        teile = zeile.split(' ', 1)
        karten_name = teile[1] if teile[0].isdigit() and len(teile) > 1 else zeile
        daten = hole_karten_daten(karten_name)
        if daten:
            name = daten.get('name')
            text = extrahiere_regeltext(daten)
            gesammelte_texte += f"KARTE: {name}\nREGELTEXT: {text}\n---\n"
        time.sleep(0.1)
    return gesammelte_texte

def ki_strategie_analyse_free(karten_daten):
    name = karten_daten.get("name")
    typ = karten_daten.get("type_line")
    text = extrahiere_regeltext(karten_daten)
    prompt = f"Erkläre Strategien für: {name} ({typ}). Effekt: {text}. Antworte auf Deutsch."
    response = client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    return response.text

# NEU: Spezifische KI-Suche für Einzelkarten-Combos in der Sammlung!
def ki_einzelkarte_combo_analyse(karten_daten):
    name = karten_daten.get("name")
    text = extrahiere_regeltext(karten_daten)
    prompt = f"""
    DU BIST EIN MTG PROFI UND COMBO-EXPERTE. DEINE KREATIVITÄT IST 0 (Faktenbasiert).
    
    Karte: {name}
    Echter Regeltext: {text}
    
    Nenne mir exakt 3 existierende, extrem starke Karten, die mit dieser spezifischen Karte eine direkte Synergie oder eine bekannte Combo bilden.
    Erkläre bei jeder der 3 Karten kurz auf Deutsch, WARUM sie so gut zusammenpassen (Regel-Logik).
    Erfinde keine Karten oder Mechaniken!
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    return response.text

def ki_deck_analyse_mit_datenbank(deck_liste, echte_combos_text, alle_karten_fakten):
    prompt = f"""
    DU BIST EIN ROBOTER FÜR REGEL-ANALYSE. DEINE KREATIVITÄT IST 0. DU LÜGST NIE.
    HIER SIND DIE EXAKTEN DATEN AUS DER SCRYFALL DATENBANK. DIESE SIND DAS EINZIGE GESETZ:
    {alle_karten_fakten}
    VERIFIZIERTE COMBOS AUS DER DATENBANK:
    {echte_combos_text}
    ANTWORTE ZWINGEND IN DIESEM FORMAT:
    ### 1. Zitat des Commanders
    Kopiere hier Wort-für-Wort den englischen Regeltext des Commanders.
    ### 2. Harte Regelprüfung
    Erkläre auf Deutsch, was diese Karte nach den offiziellen MTG-Regeln tut. 
    ### 3. Deck-Strategie
    Wie gewinnt das Deck auf Basis der echten Karten?
    ### 4. Combos & Synergien
    Zitiere die übergebenen Combos. Wenn keine gefunden wurden, schreibe "Keine unendlichen Combos". Erfinde keine.
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0)
    )
    return response.text


# --- UI ARCHITEKTUR & SITZUNGSVERWALTUNG ---
streamlit_app.set_page_config(page_title="MTG App Pro", layout="wide")

if 'eingeloggt' not in streamlit_app.session_state:
    streamlit_app.session_state['eingeloggt'] = False
    streamlit_app.session_state['benutzername'] = ""
if 'angesehene_karte' not in streamlit_app.session_state:
    streamlit_app.session_state['angesehene_karte'] = None

# --- LOGIN BEREICH ---
if not streamlit_app.session_state['eingeloggt']:
    streamlit_app.title("🔒 MTG App Pro - Login")
    
    tab_login, tab_register = streamlit_app.tabs(["Login", "Registrieren"])
    
    with tab_login:
        streamlit_app.subheader("Einloggen")
        login_name = streamlit_app.text_input("Benutzername", key="login_name")
        login_pass = streamlit_app.text_input("Passwort", type="password", key="login_pass")
        if streamlit_app.button("Einloggen"):
            if login_nutzer(login_name, login_pass):
                streamlit_app.session_state['eingeloggt'] = True
                streamlit_app.session_state['benutzername'] = login_name
                streamlit_app.rerun()
            else:
                streamlit_app.error("Falscher Benutzername oder Passwort.")
                
    with tab_register:
        streamlit_app.subheader("Konto erstellen")
        reg_name = streamlit_app.text_input("Wähle einen Benutzernamen", key="reg_name")
        reg_pass = streamlit_app.text_input("Wähle ein Passwort", type="password", key="reg_pass")
        if streamlit_app.button("Registrieren"):
            if len(reg_name) < 3:
                streamlit_app.error("Name zu kurz.")
            else:
                if registriere_nutzer(reg_name, reg_pass):
                    streamlit_app.success("Konto erstellt! Bitte wechsle zum Login.")
                else:
                    streamlit_app.error("Benutzername schon vergeben.")

# --- HAUPT APP (Eingeloggt) ---
else:
    aktiver_nutzer = streamlit_app.session_state['benutzername']
    
    with streamlit_app.sidebar:
        streamlit_app.write(f"Willkommen, **{aktiver_nutzer}**!")
        if streamlit_app.button("Ausloggen"):
            streamlit_app.session_state['eingeloggt'] = False
            streamlit_app.session_state['benutzername'] = ""
            streamlit_app.rerun()
            
    streamlit_app.title("🧙‍♂️ MTG KI-Strategie & Deck Planer")

    tab1, tab2, tab3, tab4 = streamlit_app.tabs([
        "🔍 Einzelkarte", "🎴 Deck-Analyse", "📁 Meine Decks", "📚 Meine Sammlung"
    ])

    # --- TAB 1: EINZELKARTE ---
    with tab1:
        karten_eingabe = streamlit_app.text_input("Kartenname:", "Brazen Borrower")
        spalte_suche, spalte_speichern = streamlit_app.columns([1, 4])
        with spalte_suche:
            suche_start = streamlit_app.button("Karte analysieren")
            
        if suche_start:
            with streamlit_app.spinner("Suche..."):
                daten = hole_karten_daten(karten_eingabe)
                if daten:
                    spalte_links, spalte_rechts = streamlit_app.columns([1, 2])
                    with spalte_links:
                        bild_url = daten.get("image_uris", {}).get("normal")
                        if not bild_url and "card_faces" in daten:
                            bild_url = daten["card_faces"][0].get("image_uris", {}).get("normal")
                        if bild_url: streamlit_app.image(bild_url, use_container_width=True)
                        
                        preis_eur = daten.get('prices', {}).get('eur', 'Nicht verfügbar')
                        streamlit_app.write(f"🏷️ **Marktpreis:** {preis_eur} €")
                        
                        if streamlit_app.button("In Sammelordner legen 📚"):
                            speichere_karte(aktiver_nutzer, daten.get('name'))
                            streamlit_app.success(f"{daten.get('name')} wurde gespeichert!")
                            
                    with spalte_rechts:
                        streamlit_app.write(ki_strategie_analyse_free(daten))

    # --- TAB 2: DECK-ANALYSE ---
    with tab2:
        streamlit_app.write("Deckliste hier einfügen:")
        deck_eingabe = streamlit_app.text_area("Deckliste:", height=200)
        
        col1, col2 = streamlit_app.columns(2)
        with col1:
            deck_name_input = streamlit_app.text_input("Gib dem Deck einen Namen zum Speichern:")
            if streamlit_app.button("Deck speichern 💾"):
                if deck_name_input and deck_eingabe:
                    speichere_deck(aktiver_nutzer, deck_name_input, deck_eingabe)
                    streamlit_app.success(f"Deck '{deck_name_input}' gespeichert!")
                else:
                    streamlit_app.warning("Bitte gib eine Liste und einen Namen ein.")
                    
        with col2:
            streamlit_app.write("Oder nur analysieren:")
            if streamlit_app.button("Deck analysieren 🔍"):
                with streamlit_app.spinner("Lade Fakten..."):
                    alle_karten_fakten = hole_alle_karten_texte(deck_eingabe)
                    combos_aus_db = suche_echte_combos(deck_eingabe)
                    
                    with streamlit_app.expander("🔍 KLICK HIER: Scryfall Rohdaten ansehen"):
                        streamlit_app.text(alle_karten_fakten)
                    
                    combos_text = "KEINE UNENDLICHEN COMBOS GEFUNDEN."
                    if combos_aus_db:
                        combos_text = "\n".join([f"- {c['name']}: {c['ergebnis']}" for c in combos_aus_db])
                        
                    analyse_ergebnis = ki_deck_analyse_mit_datenbank(deck_eingabe, combos_text, alle_karten_fakten)
                    
                    streamlit_app.subheader("📊 Analytischer Regel-Bericht")
                    streamlit_app.write(analyse_ergebnis)

    # --- TAB 3: MEINE DECKS ---
    with tab3:
        streamlit_app.subheader("Deine gespeicherten Decks")
        meine_decks = lade_decks(aktiver_nutzer)
        
        if not meine_decks:
            streamlit_app.info("Du hast noch keine Decks gespeichert.")
        else:
            for deck in meine_decks:
                deck_id = deck[0]
                deck_name = deck[1]
                deck_text = deck[2]
                
                with streamlit_app.expander(f"🎴 {deck_name}"):
                    streamlit_app.text(deck_text)
                    if streamlit_app.button("Deck löschen 🗑️", key=f"del_deck_{deck_id}"):
                        loesche_deck(deck_id)
                        streamlit_app.rerun()

    # --- TAB 4: MEINE SAMMLUNG ---
    with tab4:
        streamlit_app.subheader("Dein digitaler Sammelordner")
        
        streamlit_app.write("**Schnell-Hinzufügen:**")
        col_add1, col_add2 = streamlit_app.columns([3, 1])
        with col_add1:
            neue_karte_name = streamlit_app.text_input("Kartenname eingeben", key="schnell_add_input")
        with col_add2:
            streamlit_app.write("") 
            streamlit_app.write("")
            if streamlit_app.button("Hinzufügen ➕"):
                if neue_karte_name:
                    with streamlit_app.spinner("Prüfe..."):
                        daten = hole_karten_daten(neue_karte_name)
                        if daten and "name" in daten:
                            speichere_karte(aktiver_nutzer, daten["name"])
                            streamlit_app.success(f"{daten['name']} hinzugefügt!")
                            time.sleep(0.5)
                            streamlit_app.rerun()
                        else:
                            streamlit_app.error("Karte nicht gefunden.")
        
        streamlit_app.divider()
        
        # --- DIE NEUE KARTEN-DETAILANSICHT ---
        if streamlit_app.session_state['angesehene_karte']:
            karten_daten = hole_karten_daten(streamlit_app.session_state['angesehene_karte'])
            if karten_daten:
                c_bild, c_info = streamlit_app.columns([1, 2])
                with c_bild:
                    bild_url = karten_daten.get("image_uris", {}).get("normal")
                    if not bild_url and "card_faces" in karten_daten:
                        bild_url = karten_daten["card_faces"][0].get("image_uris", {}).get("normal")
                    if bild_url: streamlit_app.image(bild_url, use_container_width=True)
                    
                    if streamlit_app.button("Ansicht schließen ⬆️"):
                        streamlit_app.session_state['angesehene_karte'] = None
                        streamlit_app.rerun()
                        
                with c_info:
                    streamlit_app.subheader(karten_daten.get('name'))
                    preis = karten_daten.get('prices', {}).get('eur', 'Nicht verfügbar')
                    streamlit_app.write(f"🏷️ **Aktueller Marktpreis:** {preis} €")
                    
                    # Automatischer Combo-Report für diese Einzelkarte!
                    with streamlit_app.spinner("KI berechnet die besten Synergien für diese Karte..."):
                        combo_bericht = ki_einzelkarte_combo_analyse(karten_daten)
                        streamlit_app.write("### 🔥 KI Combo-Empfehlungen")
                        streamlit_app.write(combo_bericht)
                        
            streamlit_app.divider()
        
        # --- Liste der gespeicherten Karten ---
        meine_sammlung = lade_sammlung(aktiver_nutzer)
        if not meine_sammlung:
            streamlit_app.info("Dein Ordner ist noch leer.")
        else:
            for karte in meine_sammlung:
                karten_id = karte[0]
                karten_name = karte[1]
                
                # Angepasste Spalten für mehr Übersichtlichkeit
                c1, c2, c3 = streamlit_app.columns([3, 1, 1])
                c1.write(f"🃏 **{karten_name}**")
                
                # Der neue Detail & Combo Button!
                if c2.button("Details & Combos 🔍", key=f"view_{karten_id}"):
                    streamlit_app.session_state['angesehene_karte'] = karten_name
                    streamlit_app.rerun()
                    
                if c3.button("Entfernen ❌", key=f"del_card_{karten_id}"):
                    loesche_karte(karten_id)
                    if streamlit_app.session_state['angesehene_karte'] == karten_name:
                        streamlit_app.session_state['angesehene_karte'] = None
                    streamlit_app.rerun()