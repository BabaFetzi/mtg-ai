import requests
from google import genai

# 1. Hier deinen echten, kostenlosen Gemini API Key eintragen!
client = genai.Client(api_key=")

def hole_karten_daten(karten_name):
    """Holt die exakten Daten von Scryfall"""
    url = f"https://api.scryfall.com/cards/named?exact={karten_name}"
    antwort = requests.get(url)
    if antwort.status_code == 200:
        return antwort.json()
    return None

def ki_strategie_analyse_free(karten_daten):
    """Schickt die Kartendaten an die kostenlose Gemini KI"""
    name = karten_daten.get("name")
    typ = karten_daten.get("type_line")
    text = karten_daten.get("oracle_text")
    
    # Der Auftrag an Gemini
    prompt = f"""
    Du bist ein absoluter Magic: The Gathering Profi-Spieler und Schiedsrichter (Judge Level 3).
    Deine Aufgabe ist es, dem Nutzer strategische Tipps, Synergien und bekannte Combos zu einer Karte zu erklären.
    Antworte immer auf Deutsch, sei präzise und erfinde keine Regeln.
    
    Hier sind die echten Spieldaten der Karte aus der Scryfall-Datenbank:
    Name: {name}
    Typ: {typ}
    Kartentext: {text}
    
    Bitte analysiere diese Karte für mich:
    1. Was ist die Hauptstrategie dieser Karte?
    2. Mit welchen anderen Kartentypen oder Mechaniken harmoniert sie besonders gut (Synergien)?
    3. Nenne mir mindestens eine bekannte Combo oder starke Interaktion, falls es eine gibt.
    """
    
    # Wir rufen das kostenlose Modell auf
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    return response.text

# --- HAUPTPROGRAMM ---
gesuchte_karte = "Krenko, Mob Boss"  # Hier kannst du jede beliebige englische Karte eintragen

print(f"Suche nach '{gesuchte_karte}' in der Scryfall-Datenbank...")
daten = hole_karten_daten(gesuchte_karte)

if daten:
    print("Karte gefunden! Die kostenlose Gemini-KI analysiert die Strategie... Bitte warten...\n")
    analyse = ki_strategie_analyse_free(daten)
    print("=== KOSTENLOSE KI STRATEGIE ANALYSE ===")
    print(analyse)
    print("=======================================")
else:
    print("Karte nicht gefunden. Bitte englischen Namen prüfen!")