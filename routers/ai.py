"""
routers/ai.py – KI-gestützte Synergie-Scanner, Judge Chat & Combo Finder

Endpoints:
    POST /api/judge                       – MTG Judge Regelfragen beantworten (Premium)
    GET  /api/combos/{card_name}          – Kombos für eine Karte finden (Premium, async background task)
    POST /api/scan_combos                 – Gesamtes Deck nach bekannten Kombinationen scannen (Premium, async background task)
    GET  /api/scan_combos/status/{job_id} – Status und Ergebnis des Kombo-Scans abfragen

Abhängigkeiten:
    - database                  → get_db_session(), check_user_premium()
    - services.ai_service        → model_lite
    - services.cache             → scryfall_cache (HybridCache-Singleton)
    - services.usage_limiter     → check_and_increment_ai_usage()
"""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Depends
from pydantic import BaseModel
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session, check_user_premium
from services.cache import scryfall_cache
from services.ai_service import model_lite
from services.combos import detect_local_combos
from services.combo_validation import validate_combos
from services.limiter import limiter
from services.scryfall import parse_decklist
from services.usage_limiter import check_and_increment_ai_usage

logger = logging.getLogger(__name__)

# ======================================================================
# Lokale Request Models (zur API-Kompatibilität)
# ======================================================================
class JudgeRequest(BaseModel):
    frage: str
    benutzername: str = ""

class ScanCombosReq(BaseModel):
    karten_liste: str
    benutzername: str = ""
    format: str = "commander"

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["KI & Tools"],
)

# ======================================================================
# POST /api/judge – KI MTG-Judge
# ======================================================================
@router.post(
    "/judge",
    summary="KI Judge Regelfrage stellen",
)
@limiter.limit("10/minute")
async def judge_endpoint(req: JudgeRequest, request: Request, current_user: str = Depends(get_current_user)):
    is_premium = await check_user_premium(current_user)
    if not is_premium:
        return {
            # "error": "paywall" hier ergänzt, damit das Frontend die Paywall
            # mit demselben Feld erkennt wie bei /deck/analyse, /deck/roast,
            # /combos und /scan_combos -- "antwort" bleibt für bestehende
            # Konsumenten/Tests erhalten, die den Chat-Text direkt lesen.
            "error": "paywall",
            "antwort": "PAYWALL: Der KI-Judge steht nur Premium-Mitgliedern zur Verfügung. Bitte upgrade deine Rolle im Premium-Tab!"
        }

    if not check_and_increment_ai_usage(current_user):
        return {
            "antwort": "Du hast dein monatliches KI-Anfragen-Limit erreicht. Es setzt sich zu Beginn des nächsten Monats zurück."
        }

    if model_lite:
        try:
            response = model_lite.generate_content(f"Beantworte diese Magic The Gathering Regelfrage kurz auf Deutsch: {req.frage}")
            return {"antwort": response.text}
        except Exception:
            logger.exception("Error calling judge model")

    return {"antwort": "Der KI-Judge ist momentan beschäftigt oder nicht eingerichtet. Bitte überprüfe deinen API Key."}

# ======================================================================
# GET /api/combos/{card_name} – Kombo-Vorschläge für Einzelkarten
# ======================================================================
@router.get(
    "/combos/{card_name}",
    summary="Kombos für eine Karte finden",
)
async def get_combos(
    card_name: str,
    background_tasks: BackgroundTasks,
    format: str = "commander",
    current_user: str = Depends(get_current_user),
):
    is_premium = await check_user_premium(current_user)
    if not is_premium:
        return {
            "error": "paywall",
            "empfehlungen": [],
            "message": "Der KI-Synergie-Scanner steht nur Premium-Mitgliedern zur Verfügung."
        }

    cache_key = f"combos:{card_name.lower().strip()}:{format.lower().strip()}"
    cached = scryfall_cache.get(cache_key)
    if cached:
        return {"status": "completed", "result": cached}

    job_id = str(uuid.uuid4())
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO synergy_jobs (job_id, status, result) VALUES (:job_id, 'processing', NULL)"),
            {"job_id": job_id}
        )

    background_tasks.add_task(run_combos_bg, job_id, card_name, format, cache_key, current_user)
    return {"status": "processing", "job_id": job_id}

# ======================================================================
# POST /api/scan_combos – Deck auf Kombinationen prüfen
# ======================================================================
@router.post(
    "/scan_combos",
    summary="Deckliste auf Kombos scannen",
)
@limiter.limit("5/minute")
async def scan_combos(req: ScanCombosReq, background_tasks: BackgroundTasks, request: Request, current_user: str = Depends(get_current_user)):
    is_premium = await check_user_premium(current_user)
    if not is_premium:
        return {
            "error": "paywall",
            "combos": [],
            "message": "Der KI-Synergie-Scanner steht nur Premium-Mitgliedern zur Verfügung."
        }

    # Caching basierend auf sortiertem Deck-Hash
    parsed = parse_decklist(req.karten_liste)
    sorted_names = sorted(list({c["name"].lower().strip() for c in parsed if c.get("name")}))
    deck_str = ",".join(sorted_names)
    deck_hash = hashlib.sha256(deck_str.encode("utf-8")).hexdigest()
    cache_key = f"scan_combos:{deck_hash}:{req.format.lower().strip()}"

    cached = scryfall_cache.get(cache_key)
    if cached:
        return cached

    job_id = str(uuid.uuid4())
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO synergy_jobs (job_id, status, result) VALUES (:job_id, 'processing', NULL)"),
            {"job_id": job_id}
        )

    background_tasks.add_task(run_scan_combos_bg, job_id, req.karten_liste, current_user, req.format, cache_key)
    return {"status": "processing", "job_id": job_id}

# ======================================================================
# GET /api/scan_combos/status/{job_id} – Scan-Status abfragen
# ======================================================================
@router.get(
    "/scan_combos/status/{job_id}",
    summary="Status eines Combo-Scans abfragen",
)
async def get_scan_status(job_id: str, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT status, result FROM synergy_jobs WHERE job_id = :job_id"),
            {"job_id": job_id}
        )
        row = res.mappings().first()
        
    if not row:
        return {"status": "failed", "error": "Job nicht gefunden"}
        
    status_str = row["status"]
    result = None
    if row["result"]:
        try:
            result = json.loads(row["result"])
        except Exception:
            result = row["result"]
            
    return {"status": status_str, "result": result}


# ======================================================================
# Asynchrone Background Workers
# ======================================================================
async def run_scan_combos_bg(job_id: str, karten_liste: str, benutzername: str, format_name: str, cache_key: str):
    import httpx
    try:
        parsed = parse_decklist(karten_liste)
        raw_card_names = [c["name"] for c in parsed if c.get("name")]

        # Translate card names to official English names via Scryfall cache/API
        from services.scryfall import fetch_card_details_cached
        scryfall_data = await fetch_card_details_cached(raw_card_names)

        card_names = []
        for name in raw_card_names:
            clean_key = name.lower().strip()
            if clean_key in scryfall_data:
                resolved_name = scryfall_data[clean_key]["name"]
                # Clean DFC / split card slashes for Spellbook API
                if "//" in resolved_name:
                    resolved_name = resolved_name.split("//")[0].strip()
                card_names.append(resolved_name)
            else:
                if "//" in name:
                    name = name.split("//")[0].strip()
                card_names.append(name)

        # 1. Lokalen Combo-Check ausführen (Dauer: <5ms) mit den übersetzten Namen
        translated_decklist = "\n".join(card_names)
        local_combos = detect_local_combos(translated_decklist)
        
        # 2. Commander Spellbook API scan
        spellbook_combos = []
        
        if card_names:
            try:
                payload = {"main": [{"card": name} for name in card_names]}
                resp = httpx.post("https://backend.commanderspellbook.com/find-my-combos", json=payload, timeout=10.0)
                if resp.status_code == 200:
                    resp_data = resp.json()
                    results = resp_data.get("results", {})
                    included = results.get("included", [])
                    for combo in included:
                        legalities = combo.get("legalities", {})
                        is_legal = legalities.get(format_name.lower().strip(), True)
                        if not is_legal:
                            continue
                        
                        uses = [u["card"]["name"] for u in combo.get("uses", []) if "card" in u]
                        combo_name = " + ".join(uses)
                        
                        produces = [p["feature"]["name"] for p in combo.get("produces", []) if "feature" in p]
                        produces_str = ", ".join(produces)
                        
                        desc = combo.get("description", "")
                        grund = f"Ergebnis: {produces_str}. Ablauf: {desc}" if produces_str else desc
                        
                        spellbook_combos.append({
                            "name": combo_name,
                            "grund": grund
                        })
            except Exception:
                logger.exception("Error calling Spellbook API in run_scan_combos_bg")

        # 3. Merge combos (Duplikate vermeiden)
        merged_combos = list(local_combos)
        seen_names = {c["name"].lower().strip() for c in local_combos}
        
        for c in spellbook_combos:
            c_name = c["name"]
            if c_name.lower().strip() not in seen_names:
                merged_combos.append(c)
                seen_names.add(c_name.lower().strip())

        # 4. Fallback zu Gemini AI falls keine Combos gefunden wurden oder API fehlschlug (run_scan_combos_bg)
        if not merged_combos and model_lite and check_and_increment_ai_usage(benutzername):
            prompt = (
                "Du bist ein präziser Magic: The Gathering Schiedsrichter und Combo-Datenbank-Experte.\n"
                f"Analysiere diese Liste von Karten und finde NUR echte, spielentscheidende Combos (z.B. Infinite Mana, Infinite Damage, Instant Win) im Format '{format_name}'.\n\n"
                "Regeln zur Vermeidung von Halluzinationen:\n"
                "- Erfinde NIEMALS Synergien oder Combos. Ein bloßes Zusammenspiel (z. B. 'Sol Ring macht Mana für eine teure Kreatur' oder 'Wald erlaubt es, grüne Zauber zu spielen') ist KEINE Combo!\n"
                "- Melde nur weltbekannte, offizielle Turnier- oder Commander-Combos.\n"
                "- Wenn keine echten, bekannten Combos in der Liste vorhanden sind, gib `{\"combos\": []}` zurück.\n\n"
                "Gib das Ergebnis auf Deutsch EXAKT als JSON mit dem Schlüssel 'combos' "
                "(eine Liste von Objekten, jedes mit 'name' (Kartenname + Kartenname) und 'grund' (kurze Erklärung)) zurück (ohne Markdown Code Block).\n\n"
                f"Kartenliste:\n{karten_liste}"
            )
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: model_lite.generate_content(prompt))
                text_resp = response.text
                match = re.search(r'\{.*\}', text_resp, re.DOTALL)
                if match:
                    text_resp = match.group(0)
                json_data = json.loads(text_resp)
                if isinstance(json_data, dict) and isinstance(json_data.get("combos"), list):
                    # KI-Combos gegen Scryfall validieren (Existenz + Format-Legalität),
                    # bevor sie übernommen werden -- fängt halluzinierte Karten und
                    # format-illegale Kombinationen ab.
                    kandidaten = [
                        {
                            "name": c.get("name", ""),
                            "grund": c.get("grund") or c.get("erklaerung") or "Keine Erklärung verfügbar.",
                        }
                        for c in json_data["combos"]
                        if c.get("name")
                    ]
                    valide, verworfen = await validate_combos(kandidaten, format_name)
                    if verworfen:
                        logger.info(
                            "run_scan_combos_bg: %d KI-Combo(s) als unverifizierbar verworfen",
                            len(verworfen),
                        )
                    for c in valide:
                        if c["name"].lower().strip() not in seen_names:
                            merged_combos.append(c)
                            seen_names.add(c["name"].lower().strip())
            except Exception:
                logger.exception("Error calling Gemini in run_scan_combos_bg")

        result_data = {"combos": merged_combos}
        status_val = "completed"
        result_val = json.dumps(result_data)
        
        # In Cache speichern
        scryfall_cache.set(cache_key, result_data)
        
    except Exception as e:
        logger.exception("Error in background combo scanner")
        status_val = "failed"
        result_val = json.dumps({"error": str(e)})

    try:
        async with get_db_session() as session:
            await session.execute(
                text("UPDATE synergy_jobs SET status = :status, result = :result WHERE job_id = :job_id"),
                {"status": status_val, "result": result_val, "job_id": job_id}
            )
    except Exception:
        logger.exception("DB Error updating synergy job %s", job_id)


async def run_combos_bg(job_id: str, card_name: str, format_name: str, cache_key: str, benutzername: str = ""):
    import httpx
    try:
        # Translate card_name to official English name
        from services.scryfall import fetch_card_details_cached
        scryfall_data = await fetch_card_details_cached([card_name])
        clean_key = card_name.lower().strip()
        if clean_key in scryfall_data:
            card_name = scryfall_data[clean_key]["name"]
            
        # Clean DFC / split card slashes for Spellbook API variants compat
        if "//" in card_name:
            card_name = card_name.split("//")[0].strip()

        spellbook_combos = []
        try:
            resp = httpx.get("https://backend.commanderspellbook.com/variants/", params={"q": card_name}, timeout=10.0)
            if resp.status_code == 200:
                resp_data = resp.json()
                results = resp_data.get("results", [])
                for combo in results:
                    legalities = combo.get("legalities", {})
                    is_legal = legalities.get(format_name.lower().strip(), True)
                    if not is_legal:
                        continue
                    
                    uses = [u["card"]["name"] for u in combo.get("uses", []) if "card" in u]
                    combo_name = " + ".join(uses)
                    
                    produces = [p["feature"]["name"] for p in combo.get("produces", []) if "feature" in p]
                    produces_str = ", ".join(produces)
                    
                    desc = combo.get("description", "")
                    grund = f"Ergebnis: {produces_str}. Ablauf: {desc}" if produces_str else desc
                    
                    spellbook_combos.append({
                        "name": combo_name,
                        "grund": grund
                    })
        except Exception:
            logger.exception("Error calling Spellbook API in run_combos_bg")

        # Fallback zu Gemini AI falls Spellbook keine Ergebnisse liefert
        if not spellbook_combos and model_lite and check_and_increment_ai_usage(benutzername):
            prompt = (
                "Du bist ein präziser Magic: The Gathering Schiedsrichter und Combo-Datenbank-Experte.\n"
                f"Finde bekannte Magic The Gathering Kombinationen (Combos) für die Karte '{card_name}' im Format '{format_name}'.\n\n"
                "Regeln zur Vermeidung von Halluzinationen:\n"
                "- Erfinde NIEMALS Combos. Wenn es keine weltbekannten Combos für diese Karte gibt, gib `{\"empfehlungen\": []}` zurück.\n"
                "- Ein bloßes Zusammenspiel (z.B. 'Sol Ring macht Mana für diese Karte') ist KEINE Combo!\n\n"
                "Antworte auf Deutsch und gib das Ergebnis EXAKT als JSON mit dem Schlüssel 'empfehlungen' "
                "(eine Liste von Objekten, jedes mit 'name' (z.B. Card1 + Card2) und 'grund' (Erklärung)) zurück (ohne Markdown Code Block)."
            )
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: model_lite.generate_content(prompt))
                text_resp = response.text
                match = re.search(r'\{.*\}', text_resp, re.DOTALL)
                if match:
                    text_resp = match.group(0)
                json_data = json.loads(text_resp)
                if isinstance(json_data, dict) and isinstance(json_data.get("empfehlungen"), list):
                    # KI-Ausgabe gegen echte Kartendaten (Scryfall) validieren, um
                    # Halluzinationen abzufangen: erfundene Karten oder im Format
                    # illegale/unmögliche Combos werden verworfen.
                    valide, verworfen = await validate_combos(
                        json_data["empfehlungen"], format_name, required_card=card_name
                    )
                    if verworfen:
                        logger.info(
                            "run_combos_bg: %d KI-Combo(s) als unverifizierbar verworfen",
                            len(verworfen),
                        )
                    spellbook_combos = valide
            except Exception:
                logger.exception("Error calling Gemini in run_combos_bg")

        # Bewusst KEIN erfundener Fallback mehr: Wenn weder Commander Spellbook noch
        # die (validierte) KI eine echte Combo finden, ist die ehrliche Antwort eine
        # leere Liste. Früher wurden hier Fake-"Combos" wie "<Karte> + Sol Ring"
        # erzeugt -- also genau die Art Nicht-Combo, vor der der Prompt selbst warnt.
        result_data = {"empfehlungen": spellbook_combos}
        status_val = "completed"
        result_val = json.dumps(result_data)
        scryfall_cache.set(cache_key, result_data)

    except Exception as e:
        logger.exception("Error in background single combos fetcher")
        status_val = "failed"
        result_val = json.dumps({"error": str(e)})

    try:
        async with get_db_session() as session:
            await session.execute(
                text("UPDATE synergy_jobs SET status = :status, result = :result WHERE job_id = :job_id"),
                {"status": status_val, "result": result_val, "job_id": job_id}
            )
    except Exception:
        logger.exception("DB Error updating single combo job %s", job_id)
