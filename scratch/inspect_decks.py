import sqlite3

conn = sqlite3.connect("mtg_app.db")
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, deck_name, deck_liste, format FROM decks WHERE id = 14;")
    row = cursor.fetchone()
    if row:
        print(f"Deck ID: {row[0]}")
        print(f"Deck Name: '{row[1]}'")
        print(f"Format: {row[3]}")
        print("Cards:")
        print(repr(row[2]))
    else:
        print("Deck not found")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
