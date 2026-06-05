import httpx
import json

url = "https://backend.commanderspellbook.com/find-my-combos"

cards = ["Thassa's Oracle", "Demonic Consultation", "Sol Ring"]

# Format A (cards list)
payload_a = {"cards": cards}

# Format B (main list)
payload_b = {"main": [{"card": name} for name in cards]}

print("Testing Format A (cards list):")
try:
    resp = httpx.post(url, json=payload_a, timeout=10.0)
    print("Format A Status:", resp.status_code)
    data = resp.json()
    print("Format A Results count:", len(data.get("results", {}).get("included", [])))
except Exception as e:
    print("Format A Error:", e)

print("\nTesting Format B (main list):")
try:
    resp = httpx.post(url, json=payload_b, timeout=10.0)
    print("Format B Status:", resp.status_code)
    data = resp.json()
    print("Format B Results count:", len(data.get("results", {}).get("included", [])))
except Exception as e:
    print("Format B Error:", e)
