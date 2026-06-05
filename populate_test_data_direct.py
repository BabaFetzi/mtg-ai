import asyncio
import os
import sys
import sqlite3

# Set python path to allow importing application modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "OneDrive", "Desktop", "mtg_ai")))

# Import scryfall service to pre-fetch real images and prices
from services.scryfall import fetch_card_details_cached

album_cards = {
    "Tauschordner": [
        "Sol Ring",
        "Arcane Signet",
        "Command Tower",
        "Demonic Tutor",
        "Rhystic Study",
        "Cyclonic Rift"
    ],
    "Rare Binder": [
        "Sheoldred, the Apocalypse",
        "Great Henge",
        "Doubling Season",
        "Esper Sentinel",
        "Ledger Shredder",
        "Boseiju, Who Endures"
    ],
    "Commander Foils": [
        "Mana Crypt",
        "Jeweled Lotus",
        "Mox Diamond",
        "Grim Monolith",
        "Wheel of Fortune",
        "Chrome Mox"
    ],
    "Standard Staples": [
        "Lightning Bolt",
        "Orcish Bowmasters",
        "Ragavan, Nimble Pilferer",
        "Murktide Regent",
        "Teferi, Time Raveler",
        "Polluted Delta"
    ]
}

wishlist = [
    "Black Lotus",
    "Mox Sapphire",
    "Mox Ruby",
    "Mox Jet",
    "Mox Emerald",
    "Mox Pearl",
    "Time Walk",
    "Ancestral Recall",
    "Timetwister",
    "Mana Vault",
    "Lotus Petal",
    "Mox Diamond"
]

deck1_list = """1 Beledros Witherbloom
1 Dina, Soul Steeper
1 Witherbloom Apprentice
1 Sol Ring
1 Arcane Signet
1 Command Tower
1 Overgrown Tomb
1 Verdant Catacombs
1 Woodland Cemetery
1 Dark Ritual
1 Demonic Tutor
1 Vampiric Tutor
1 Heroic Intervention
1 Assassin's Trophy
1 Abrupt Decay
1 Cultivate
1 Kodama's Reach
1 Eternal Witness
1 Skullclamp
1 Sanguine Bond
1 Exquisite Blood
1 Sylvan Library
1 Necropotence
1 Phyrexian Arena
1 Toxic Deluge
1 Beast Within
1 Bojuka Bog
1 Reliquary Tower
10 Forest
10 Swamp"""

deck2_list = """4 Ragavan, Nimble Pilferer
4 Dragon's Rage Channeler
4 Murktide Regent
2 Ledger Shredder
4 Lightning Bolt
4 Counterspell
4 Consider
4 Expressive Iteration
4 Unholy Heat
2 Spell Pierce
4 Polluted Delta
4 Scalding Tarn
2 Steam Vents
2 Spirebluff Canal
2 Island
2 Mountain"""

deck3_list = """3 Teferi, Temporal Pilgrim
4 Sheoldred, the Apocalypse
3 Wandering Emperor
4 Make Disappear
4 Go for the Throat
4 Cut Down
4 Void Rend
4 Memory Deluge
2 Depopulate
4 Raffine's Tower
4 Shipwreck Marsh
4 Shattered Sanctuary
4 Deserted Beach
2 Island
2 Swamp
2 Plains"""

async def main():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mtg_app.db"))
    print(f"Using database at: {db_path}")
    
    # 1. Clean old data for user Babafetzi
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM decks WHERE LOWER(benutzername) = 'babafetzi'")
    cursor.execute("DELETE FROM sammlung_alben WHERE LOWER(benutzername) = 'babafetzi'")
    conn.commit()
    print("Deleted existing decks and collection entries for user Babafetzi.")
    
    # 2. Collect card names to fetch Scryfall data
    all_cards = set()
    for cards in album_cards.values():
        all_cards.update(cards)
    all_cards.update(wishlist)
    
    print(f"Fetching details for {len(all_cards)} cards from Scryfall cache/API...")
    scryfall_data = await fetch_card_details_cached(list(all_cards))
    print(f"Successfully loaded metadata for {len(scryfall_data)} cards.")
    
    # 3. Insert albums
    for album_name, cards in album_cards.items():
        for card_name in cards:
            card_info = scryfall_data.get(card_name.lower().strip())
            if card_info:
                bild_url = card_info.get("image", "")
                preis = card_info.get("price", "0.00")
            else:
                bild_url = ""
                preis = "0.00"
            
            cursor.execute(
                "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) VALUES (?, ?, ?, ?, ?)",
                ("Babafetzi", card_name, album_name, bild_url, str(preis))
            )
            print(f"Added {card_name} to album '{album_name}'")
            
    # 4. Insert wishlist entries
    for card_name in wishlist:
        card_info = scryfall_data.get(card_name.lower().strip())
        if card_info:
            bild_url = card_info.get("image", "")
            preis = card_info.get("price", "0.00")
        else:
            bild_url = ""
            preis = "0.00"
        
        cursor.execute(
            "INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) VALUES (?, ?, ?, ?, ?)",
            ("Babafetzi", card_name, "Wunschliste", bild_url, str(preis))
        )
        print(f"Added {card_name} to Wunschliste")
        
    # 5. Insert decks
    decks = [
        {
            "name": "Witherbloom Midrange",
            "format": "commander",
            "liste": deck1_list
        },
        {
            "name": "Izzet Murktide",
            "format": "modern",
            "liste": deck2_list
        },
        {
            "name": "Esper Control",
            "format": "standard",
            "liste": deck3_list
        }
    ]
    
    for d in decks:
        cursor.execute(
            "INSERT INTO decks (benutzername, deck_name, deck_liste, format) VALUES (?, ?, ?, ?)",
            ("Babafetzi", d["name"], d["liste"], d["format"])
        )
        print(f"Added deck '{d['name']}' ({d['format']})")
        
    conn.commit()
    conn.close()
    print("Database population completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
