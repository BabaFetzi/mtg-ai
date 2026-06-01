import requests

def hole_karten_infos(karten_name):
    # Wir fragen die offizielle Scryfall-Datenbank nach der Karte
    url = f"https://api.scryfall.com/cards/named?exact={karten_name}"
    antwort = requests.get(url)
    
    if antwort.status_code == 200:
        daten = antwort.json()
        
        # Hier ziehen wir die wichtigsten Infos heraus
        name = daten.get("name")
        manakosten = daten.get("mana_cost")
        typ = daten.get("type_line")
        text = daten.get("oracle_text")
        
        print(f"--- KARTE GEFUNDEN ---")
        print(f"Name: {name}")
        print(f"Manakosten: {manakosten}")
        print(f"Typ: {typ}")
        print(f"Effekt: \n{text}")
        print(f"----------------------")
    else:
        print("Karte wurde leider nicht gefunden. Überprüfe die Schreibweise (Englisch)!")

# Testlauf: Wir suchen nach dem berühmten Black Lotus
hole_karten_infos("Black Lotus")