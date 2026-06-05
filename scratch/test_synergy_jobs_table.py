import sqlite3
import json

conn = sqlite3.connect("mtg_app.db")
cursor = conn.cursor()

try:
    cursor.execute("SELECT * FROM synergy_jobs;")
    rows = cursor.fetchall()
    print(f"Total jobs: {len(rows)}")
    for r in rows:
        print(f"ID: {r[0]}, Status: {r[1]}, Result: {r[2][:100] if r[2] else 'None'}, Created: {r[3]}")
except Exception as e:
    print("Error querying database:", e)
finally:
    conn.close()
