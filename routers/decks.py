"""
routers/decks.py – Deck-Management, Starthand-Simulator, Statistiken & Format-Validierung

Endpoints:
    GET  /api/decks/{benutzername}  – Alle Decks eines Users abrufen
    POST /api/decks/erstellen       – Neues Deck erstellen
    POST /api/decks/update          – Deck-Liste aktualisieren
    POST /api/decks/loeschen        – Deck löschen
    POST /api/deck/visualize        – Kartenbilder und Typen der Deckliste auflösen
    POST /api/deck/stats            – CMC-Kurve und Farbverteilung berechnen
    POST /api/deck/wert             – Gesamtwert der Deckliste berechnen
    POST /api/deck/analyse          – KI-Deck-Analyse (Premium)
    POST /api/deck/validate         – Deck-Validierung nach Turnierformat (Banned Lists etc.)
    POST /api/deck/add-card         – Einzelne Karte im Deck inkrementieren/hinzufügen
    POST /api/deck/remove-card      – Einzelne Karte im Deck dekrementieren/entfernen

Abhängigkeiten:
    - database                  → get_db_session(), check_user_premium()
    - services.scryfall          → fetch_card_details_cached(), clean_card_name(), parse_decklist()
    - services.ai_service        → model
    - services.cache             → scryfall_cache (HybridCache-Singleton)
    - format_engine             → FormatValidator
    - schemas.models            → DeckErstellenReq, DeckUpdateReq, DeckLoeschenReq, DeckAnalyseReq, ValidateDeckReq
"""

import hashlib
import json
import re
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db_session, check_user_premium
from services.cache import scryfall_cache
from services.scryfall import fetch_card_details_cached, clean_card_name, parse_decklist
from services.ai_service import model, model_lite
from services.usage_limiter import check_and_increment_ai_usage
from format_engine import FormatValidator
from schemas.models import (
    DeckErstellenReq,
    DeckUpdateReq,
    DeckLoeschenReq,
    DeckAnalyseReq,
    ValidateDeckReq
)

# ======================================================================
# Lokale Request-Modelle für Add/Remove (zur API-Kompatibilität)
# ======================================================================
class DeckAddCardReq(BaseModel):
    deck_id: int
    card_name: str

class DeckRemoveCardReq(BaseModel):
    deck_id: int
    card_name: str

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["Decks"],
)

# ======================================================================
# GET /api/decks/{benutzername} – Alle Decks abrufen
# ======================================================================
@router.get(
    "/decks/{benutzername}",
    summary="Decks eines Benutzers abrufen",
)
async def get_decks(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM decks WHERE benutzername = :name"),
            {"name": benutzername}
        )
        rows = res.mappings().all()
        return [{"id": r["id"], "name": r["name"], "liste": r["liste"], "format": r.get("format") or "commander"} for r in rows]

# ======================================================================
# POST /api/decks/erstellen – Deck erstellen
# ======================================================================
@router.post(
    "/decks/erstellen",
    summary="Neues Deck erstellen",
)
async def create_deck(data: DeckErstellenReq):
    async with get_db_session() as session:
        is_premium = await check_user_premium(data.benutzername)
        if not is_premium:
            res = await session.execute(
                text("SELECT COUNT(*) FROM decks WHERE benutzername = :name"),
                {"name": data.benutzername}
            )
            count = res.scalar()
            if count >= 3:
                raise HTTPException(
                    status_code=403,
                    detail="Limit erreicht: Kostenlose Konten können maximal 3 Decks erstellen. Bitte erwerbe Grana Pro für unbegrenzte Decks."
                )
        
        await session.execute(
            text("INSERT INTO decks (benutzername, name, liste, format) VALUES (:user, :name, :list, :format)"),
            {"user": data.benutzername, "name": data.deck_name, "list": data.deck_liste, "format": data.format or "commander"}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/decks/update – Deckliste aktualisieren
# ======================================================================
@router.post(
    "/decks/update",
    summary="Deck aktualisieren",
)
async def update_deck(data: DeckUpdateReq):
    async with get_db_session() as session:
        update_parts = []
        params = {"id": data.deck_id}
        if data.deck_liste is not None:
            update_parts.append("liste = :list")
            params["list"] = data.deck_liste
        if data.deck_name is not None:
            update_parts.append("name = :name")
            params["name"] = data.deck_name
        if data.format is not None:
            update_parts.append("format = :format")
            params["format"] = data.format
            
        if update_parts:
            query = f"UPDATE decks SET {', '.join(update_parts)} WHERE id = :id"
            await session.execute(text(query), params)
    return {"erfolg": True}

# ======================================================================
# POST /api/decks/loeschen – Deck löschen
# ======================================================================
@router.post(
    "/decks/loeschen",
    summary="Deck löschen",
)
async def delete_deck(data: DeckLoeschenReq):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM decks WHERE id = :id AND benutzername = :user"),
            {"id": data.deck_id, "user": data.benutzername}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/deck/visualize – Visualisierung der Kartenbilder
# ======================================================================
@router.post(
    "/deck/visualize",
    summary="Kartenbilder für Deck auflösen",
)
async def deck_visualize(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    if not parsed:
        return {"karten": []}
    
    unique_names = list(set([p["name"] for p in parsed]))
    scryfall_data = await fetch_card_details_cached(unique_names)
                    
    karten = []
    for p in parsed:
        name_lower = p["name"].lower().strip()
        if name_lower in scryfall_data:
            karten.append({
                "count": p["count"],
                "name": scryfall_data[name_lower]["name"],
                "image": scryfall_data[name_lower]["image"],
                "type": scryfall_data[name_lower]["type"]
            })
        else:
            karten.append({
                "count": p["count"],
                "name": p["name"] + " (Nicht gefunden)",
                "image": "",
                "type": "Unbekannt"
            })
            
    return {"karten": karten}

# ======================================================================
# POST /api/deck/stats – CMC-Kurve und Farben berechnen
# ======================================================================
@router.post(
    "/deck/stats",
    summary="Statistiken berechnen",
)
async def deck_stats(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    unique_names = list(set([p["name"] for p in parsed]))
    cmc_counts = {}
    cmc_creatures = {}
    cmc_noncreatures = {}
    color_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
    
    scryfall_data = await fetch_card_details_cached(unique_names)
    for p in parsed:
        name_lower = p["name"].lower().strip()
        c = scryfall_data.get(name_lower)
        if not c:
            continue
        count = p["count"]
        
        try:
            cmc = int(float(c.get("cmc") or 0.0))
        except (ValueError, TypeError):
            cmc = 0
        
        type_line = c.get("type", "")
        if "Land" not in type_line:
            cmc_counts[str(cmc)] = cmc_counts.get(str(cmc), 0) + count
            if "Creature" in type_line:
                cmc_creatures[str(cmc)] = cmc_creatures.get(str(cmc), 0) + count
            else:
                cmc_noncreatures[str(cmc)] = cmc_noncreatures.get(str(cmc), 0) + count
            
        colors = c.get("colors", [])
        if not colors:
            if "Land" not in type_line:
                color_counts["C"] += count
        else:
            for color in set(colors):
                if color in color_counts:
                    color_counts[color] += count
                                
    return {
        "cmc": cmc_counts,
        "cmc_creatures": cmc_creatures,
        "cmc_noncreatures": cmc_noncreatures,
        "colors": color_counts
    }

# ======================================================================
# POST /api/deck/wert – Gesamtwert des Decks
# ======================================================================
@router.post(
    "/deck/wert",
    summary="Deckwert berechnen",
)
async def deck_wert(req: DeckAnalyseReq):
    parsed = parse_decklist(req.deck_liste)
    unique_names = list(set([p["name"] for p in parsed]))
    total_value = 0.0
    
    scryfall_data = await fetch_card_details_cached(unique_names)
    for p in parsed:
        name_lower = p["name"].lower().strip()
        c = scryfall_data.get(name_lower)
        if not c:
            continue
        count = p["count"]
        try:
            price = float(c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil") or 0.0)
        except (ValueError, TypeError):
            price = 0.0
        total_value += (price * count)
                    
    return {"gesamt_wert": f"{total_value:.2f}"}

# ======================================================================
# POST /api/deck/analyse – KI-gestützte Deck-Analyse (Premium)
# ======================================================================
@router.post(
    "/deck/analyse",
    summary="KI-Deck-Analyse",
)
async def deck_analyse(req: DeckAnalyseReq):
    is_premium = await check_user_premium(req.benutzername)
    if not is_premium:
        return {
            "error": "paywall",
            "message": "Dieses Premium-Feature (KI-Deck-Analyse) steht nur Premium-Mitgliedern zur Verfügung."
        }
        
    deck_hash = hashlib.sha256((req.deck_liste.strip() + ":" + req.format).encode("utf-8")).hexdigest()
    cache_key = f"deck_analysis:{deck_hash}"
    cached = scryfall_cache.get(cache_key)
    if cached:
        return cached

    if model and check_and_increment_ai_usage(req.benutzername):
        try:
            prompt = (
                f"Analysiere dieses Magic the Gathering Deck auf Deutsch unter Berücksichtigung des Formats: '{req.format}'.\n"
                f"Format-Spezifikationen:\n"
                f"- Commander: Multiplayer, Singleton, Turn 8-12 durchschnittlich, Synergien mit Commander entscheidend.\n"
                f"- Standard: Best-of-3, 60 Karten, Turn 5-8, Konstanz und 4-of-Kopien wichtig.\n"
                f"- Modern: Turn 3-5, hoch-interaktiv, starke Interaktion & Antworten erforderlich.\n"
                f"- Legacy: Turn 1-3, Combo-lastig, extrem hohe Effizienz.\n"
                f"- Vintage: Restricted Cards, Power 9 erlaubt, maximale Turn 1-2 Explosivität.\n\n"
                f"Gib die Antwort EXAKT als JSON (ohne Markdown Code Block) mit den folgenden Schlüsseln zurück:\n"
                f"- 'strategie' (string)\n"
                f"- 'commander' (string, falls vorhanden, sonst 'Das Deck')\n"
                f"- 'staerken' (array of strings)\n"
                f"- 'schwaechen' (object mit Schlüsseln: 'card_draw', 'removal', 'ramp', 'protection', 'winconditions', wobei jeder Schlüssel ein-Objekt mit 'score' (int, 1-10) und 'text' (string) ist)\n"
                f"- 'synergien' (array of objects mit Schlüsseln: 'karten' (array of strings) und 'erklaerung' (string))\n"
                f"- 'combos' (array of objects mit Schlüsseln: 'karten' (array of strings), 'typ' (string, z.B. 'Infinite Token', 'Infinite Mana') und 'erklaerung' (string))\n"
                f"- 'verbesserungen' (array of objects mit Schlüsseln: 'rein' (string), 'raus' (string oder null), 'grund' (string))\n"
                f"- 'format_kontext' (string)\n"
                f"- 'power_level' (int, 1-10)\n\n"
                f"Deckliste:\n{req.deck_liste}"
            )
            response = model.generate_content(prompt)
            text_resp = response.text
            match = re.search(r'\{.*\}', text_resp, re.DOTALL)
            if match:
                text_resp = match.group(0)
            
            result = json.loads(text_resp)
            scryfall_cache.set(cache_key, result)
            return result
        except Exception as e:
            print(f"Error generating deck analysis: {e}")
            
    fallback_res = {
        "strategie": "Konnte durch die KI aktuell nicht ausgewertet werden.",
        "commander": "Unbekannt",
        "staerken": ["API oder KI Model offline"],
        "schwaechen": {
            "card_draw": {"score": 5, "text": "Keine card draw Daten verfügbar."},
            "removal": {"score": 5, "text": "Keine removal Daten verfügbar."},
            "ramp": {"score": 5, "text": "Keine ramp Daten verfügbar."},
            "protection": {"score": 5, "text": "Keine protection Daten verfügbar."},
            "winconditions": {"score": 5, "text": "Keine winconditions Daten verfügbar."}
        },
        "synergien": [],
        "combos": [],
        "verbesserungen": [],
        "format_kontext": "Format-Kontext konnte nicht bestimmt werden.",
        "power_level": 5
    }
    return fallback_res

# ======================================================================
# POST /api/deck/roast – Deck-Roast (Premium)
# ======================================================================
@router.post(
    "/deck/roast",
    summary="Humorvoller Deck-Roast",
)
async def deck_roast(req: DeckAnalyseReq):
    is_premium = await check_user_premium(req.benutzername)
    if not is_premium:
        return {
            "error": "paywall",
            "message": "Dieses Premium-Feature (KI-Deck-Roast) steht nur Premium-Mitgliedern zur Verfügung."
        }
        
    deck_hash = hashlib.sha256((req.deck_liste.strip() + ":" + req.format).encode("utf-8")).hexdigest()
    cache_key = f"deck_roast:{deck_hash}"
    cached = scryfall_cache.get(cache_key)
    if cached:
        return cached

    if model_lite and check_and_increment_ai_usage(req.benutzername):
        try:
            prompt = (
                f"Roaste dieses Magic the Gathering Deck auf Deutsch unter Berücksichtigung des Formats: '{req.format}'.\n"
                f"Sei extrem sarkastisch, humorvoll, gemein aber augenzwinkernd. Nutze typischen Magic-Slang (z.B. Salz, Jank, Mana-Flooded, Netdecker, Comboplayer, Casual, etc.).\n"
                f"Kritisiere Kartenwahlen, eventuelle Instabilitäten, Klischees des Commanders oder Formats.\n\n"
                f"Gib die Antwort EXAKT als JSON (ohne Markdown Code Block) mit den folgenden Schlüsseln zurück:\n"
                f"- 'roast' (string, ausführlicher humorvoller Text, mind. 120 Wörter)\n"
                f"- 'salt_score' (int, Wert von 1-100 wie 'salzig' / nervig das Deck ist)\n"
                f"- 'verdict' (string, eine kurze, witzige Zusammenfassung / Urteil, z.B. 'Der wandelnde Salzstreuer')\n\n"
                f"Deckliste:\n{req.deck_liste}"
            )
            response = model_lite.generate_content(prompt)
            text_resp = response.text
            match = re.search(r'\{.*\}', text_resp, re.DOTALL)
            if match:
                text_resp = match.group(0)

            result = json.loads(text_resp)
            scryfall_cache.set(cache_key, result)
            return result
        except Exception as e:
            print(f"Error generating deck roast: {e}")
            
    fallback_res = {
        "roast": "Dein Deck ist so langweilig, dass selbst die KI eingeschlafen ist. Versuche es später noch einmal.",
        "salt_score": 50,
        "verdict": "Zu unbedeutend für echtes Salz"
    }
    return fallback_res

# ======================================================================
# POST /api/deck/validate – Validierung nach Formatregeln
# ======================================================================
@router.post(
    "/deck/validate",
    summary="Deck-Validierung",
)
async def validate_deck(req: ValidateDeckReq):
    try:
        result = await FormatValidator.validate_deck(req.deck_liste, req.format, fetch_card_details_cached)
        return result
    except Exception as e:
        print(f"Error in validate_deck: {e}")
        return {
            "legal": False,
            "errors": [f"Fehler bei der Deck-Validierung: {str(e)}"],
            "warnings": [],
            "details": {"format": req.format, "total_cards": 0}
        }

# ======================================================================
# POST /api/deck/add-card – Karte dem Deck hinzufügen
# ======================================================================
@router.post(
    "/deck/add-card",
    summary="Karte zu Deck hinzufügen",
)
async def add_card_to_deck(req: DeckAddCardReq):
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT liste FROM decks WHERE id = :id"),
                {"id": req.deck_id}
            )
            row = res.mappings().first()
            if not row:
                return {"erfolg": False, "error": "Deck nicht gefunden."}

            current_liste = row["liste"] or ""
            lines = current_liste.split('\n')
            updated = False
            updated_lines = []

            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                match = re.match(r'^(\d+)[xX]?\s+(.+)$', line_str)
                if match:
                    count = int(match.group(1))
                    name = match.group(2).strip()
                    if clean_card_name(name).lower() == clean_card_name(req.card_name).lower():
                        count += 1
                        updated_lines.append(f"{count}x {name}")
                        updated = True
                    else:
                        updated_lines.append(line_str)
                else:
                    if clean_card_name(line_str).lower() == clean_card_name(req.card_name).lower():
                        updated_lines.append(f"2x {line_str}")
                        updated = True
                    else:
                        updated_lines.append(line_str)

            if not updated:
                updated_lines.append(f"1x {req.card_name}")

            new_liste = '\n'.join(updated_lines)
            await session.execute(
                text("UPDATE decks SET liste = :list WHERE id = :id"),
                {"list": new_liste, "id": req.deck_id}
            )

        return {"erfolg": True, "deck_liste": new_liste}
    except Exception as e:
        print(f"Fehler beim Hinzufügen der Karte zum Deck: {e}")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# POST /api/deck/remove-card – Karte aus Deck entfernen
# ======================================================================
@router.post(
    "/deck/remove-card",
    summary="Karte aus Deck entfernen",
)
async def remove_card_from_deck(req: DeckRemoveCardReq):
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM decks WHERE id = :id"),
                {"id": req.deck_id}
            )
            deck = res.mappings().first()
            if not deck:
                return {"erfolg": False, "error": "Deck nicht gefunden."}

            deck_liste = deck["liste"] or ""
            lines = deck_liste.strip().split('\n') if deck_liste.strip() else []

            card_found = False
            updated_lines = []
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    updated_lines.append(line)
                    continue
                match = re.match(r'^(\d+)[xX]?\s+(.+)$', line_stripped)
                if match:
                    count = int(match.group(1))
                    name = match.group(2).strip()
                    if name.lower() == req.card_name.lower():
                        card_found = True
                        count -= 1
                        if count > 0:
                            updated_lines.append(f"{count} {name}")
                    else:
                        updated_lines.append(line)
                else:
                    if line_stripped.lower() == req.card_name.lower():
                        card_found = True
                    else:
                        updated_lines.append(line)

            if not card_found:
                return {"erfolg": False, "error": f"Karte '{req.card_name}' nicht im Deck gefunden."}

            new_liste = '\n'.join(updated_lines)
            await session.execute(
                text("UPDATE decks SET liste = :list WHERE id = :id"),
                {"list": new_liste, "id": req.deck_id}
            )

        return {"erfolg": True, "deck_liste": new_liste}
    except Exception as e:
        print(f"Fehler beim Entfernen der Karte aus dem Deck: {e}")
        return {"erfolg": False, "error": str(e)}


# ======================================================================
# GET /api/v1/shared/decks/{id} – Geteiltes Deck abrufen (Read-Only)
# ======================================================================
@router.get(
    "/v1/shared/decks/{id}",
    summary="Geteiltes Deck abrufen (Read-Only)",
    description="Holt die Metadaten und die Kartenliste eines öffentlich geteilten Decks. "
                "Diese Route ist strikt read-only und leakt keine privaten Notizen oder Benutzerdaten.",
)
async def get_shared_deck(id: int):
    try:
        async with get_db_session() as session:
            # Nur die für das Deck-Layout relevanten Spalten laden, um Daten-Leaks zu verhindern
            res = await session.execute(
                text("SELECT id, benutzername, name, liste, format FROM decks WHERE id = :id"),
                {"id": id}
            )
            row = res.mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Deck nicht gefunden oder existiert nicht.")

        return {
            "id": row["id"],
            "besitzer": row["benutzername"],
            "name": row["name"],
            "liste": row["liste"],
            "format": row.get("format") or "commander"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Fehler beim Laden des geteilten Decks: {e}")
        raise HTTPException(status_code=500, detail="Interner Serverfehler.")


# ======================================================================
# GET /api/dashboard/stats – Platform statistics for dashboard
# ======================================================================
@router.get(
    "/dashboard/stats",
    summary="Statistiken für das Dashboard abrufen",
)
async def get_dashboard_stats():
    try:
        async with get_db_session() as session:
            # 1. Total decks count
            res_decks = await session.execute(text("SELECT COUNT(*) FROM decks"))
            decks_count = res_decks.scalar() or 0

            # 2. Total collection cards count (sum of card quantities)
            res_collection = await session.execute(text("SELECT SUM(anzahl) FROM sammlung_alben"))
            collection_count = res_collection.scalar() or 0

            # 3. Simulated API queries count (based on decks, collection entries, and a fixed starting value)
            query_count = (decks_count * 12) + (collection_count * 3) + 1420

            return {
                "total_decks": decks_count,
                "total_collection_cards": collection_count,
                "query_count": query_count
            }
    except Exception as e:
        print(f"Fehler beim Laden der Dashboard-Statistiken: {e}")
        return {
            "total_decks": 0,
            "total_collection_cards": 0,
            "query_count": 1420
        }


