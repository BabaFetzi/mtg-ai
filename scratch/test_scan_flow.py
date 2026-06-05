import httpx
import time

url_scan = "http://127.0.0.1:8000/api/scan_combos"
# Godo + Helm of the Host deck list
deck_list = """
1 Godo, Bandit Warlord
1 Helm of the Host
38 Mountain
"""

payload = {
    "karten_liste": deck_list,
    "benutzername": "Babafetzi",
    "format": "commander"
}

print("Initiating scan...")
try:
    resp = httpx.post(url_scan, json=payload, timeout=10.0)
    print("Scan Response Status:", resp.status_code)
    data = resp.json()
    print("Response data:", data)
    
    if data.get("status") == "processing":
        job_id = data.get("job_id")
        url_status = f"http://127.0.0.1:8000/api/scan_combos/status/{job_id}"
        
        for _ in range(15):
            time.sleep(1.0)
            status_resp = httpx.get(url_status)
            status_data = status_resp.json()
            print("Poll Status:", status_data.get("status"))
            if status_data.get("status") == "completed":
                print("Combos found:", status_data.get("result", {}).get("combos"))
                break
            elif status_data.get("status") == "failed":
                print("Job failed:", status_data)
                break
    else:
        print("Completed directly or error:", data)
except Exception as e:
    print("Error during flow:", e)
