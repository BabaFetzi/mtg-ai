import httpx

url = "https://backend.commanderspellbook.com/find-my-combos"

# Fire // Ice + Isochron Scepter + Dramatic Reversal
cards_full = ["Fire // Ice", "Isochron Scepter", "Dramatic Reversal"]
cards_front = ["Fire", "Isochron Scepter", "Dramatic Reversal"]

payload_full = {"main": [{"card": name} for name in cards_full]}
payload_front = {"main": [{"card": name} for name in cards_front]}

print("Testing full name 'Fire // Ice':")
try:
    resp = httpx.post(url, json=payload_full, timeout=10.0)
    included = resp.json().get("results", {}).get("included", [])
    print("Combos matched:", len(included))
    for c in included:
        print(" -", c.get("name"))
except Exception as e:
    print("Error:", e)

print("\nTesting front face 'Fire':")
try:
    resp = httpx.post(url, json=payload_front, timeout=10.0)
    included = resp.json().get("results", {}).get("included", [])
    print("Combos matched:", len(included))
    for c in included:
        print(" -", c.get("name"))
except Exception as e:
    print("Error:", e)
