import httpx
import json

# Test 1: Full name with "//"
url_full = "https://backend.commanderspellbook.com/variants/?q=Fire%20//%20Ice"
# Test 2: Only front face
url_front = "https://backend.commanderspellbook.com/variants/?q=Fire"

print("Testing full name 'Fire // Ice':")
try:
    resp = httpx.get(url_full)
    print("Full name status:", resp.status_code)
    results = resp.json().get("results", [])
    print("Full name results count:", len(results))
    if results:
        print("First result name:", " + ".join([u["card"]["name"] for u in results[0]["uses"]]))
except Exception as e:
    print("Error:", e)

print("\nTesting front face 'Fire':")
try:
    resp = httpx.get(url_front)
    print("Front face status:", resp.status_code)
    results = resp.json().get("results", [])
    print("Front face results count:", len(results))
    if results:
        print("First result name:", " + ".join([u["card"]["name"] for u in results[0]["uses"]]))
except Exception as e:
    print("Error:", e)
