"""
routers/cards.py – Kartensuche & Markt-Trends

Verantwortlich für:
- GET /api/suche/{search_term}   → Einzelkarten-Suche mit Übersetzung & Prints
- GET /api/trends                → Personalisierte oder Fallback-Trending-Cards

Abhängigkeiten:
- services.cache       → scryfall_cache (HybridCache-Singleton)
- services.scryfall    → fetch_card_details_cached()
- services.ai_service  → model_lite, KI_VERFUEGBAR
- services.usage_limiter → check_and_increment_ai_usage()
- database             → get_db_session(), check_user_premium()
"""

import logging
import urllib.parse
from typing import Optional

import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy import text

from auth import get_current_user_optional
from services.cache import scryfall_cache
from services.scryfall import fetch_card_details_cached, scryfall_client, scryfall_request
from services.ai_service import model_lite, KI_VERFUEGBAR
from services.usage_limiter import check_and_increment_ai_usage
from database import get_db_session, check_user_premium
from schemas.models import CardSearchResult, TrendsResponse

logger = logging.getLogger(__name__)

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["Karten"],
)


# ======================================================================
# GET /api/suche/{search_term} – Einzelkarten-Suche
# ======================================================================
@router.get(
    "/suche/{search_term}",
    summary="Karte suchen",
    description="Sucht eine einzelne MTG-Karte über Scryfall (Fuzzy + Multilang-Fallback). "
                "Premium-User erhalten eine deutsche Übersetzung des Kartentexts via KI.",
    response_model=CardSearchResult,
)
async def suche_karte(
    search_term: str,
    current_user: str = Depends(get_current_user_optional),
):
    """
    Ablauf:
    1. Premium-Status prüfen
    2. Cache prüfen (Key = suche:{term}:{is_premium})
    3. Scryfall /cards/named?fuzzy=... aufrufen
    4. Fallback: Sprachübergreifende Suche (lang:any)
    5. Oracle-Text per Gemini KI übersetzen (nur Premium)
    6. Alle Prints (Auflagen) der Karte laden
    7. Ergebnis cachen und zurückgeben
    """
    benutzername = current_user or ""
    is_premium = await check_user_premium(benutzername) if current_user else False
    cache_key = f"suche:{search_term.lower().strip()}:{is_premium}"

    # --- Cache-Hit → sofort zurückgeben ---
    cached = scryfall_cache.get(cache_key)
    if cached:
        return cached

    async with scryfall_client() as client:
        # --- Scryfall Fuzzy-Suche ---
        url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(search_term)}"
        resp = await scryfall_request(client, "GET", url)

        # --- Fallback: Sprachübergreifende Suche ---
        if resp.status_code != 200:
            resp = await _fallback_lang_search(client, search_term, resp)

        if resp.status_code != 200:
            return {"error": "Karte nicht gefunden"}

        data = resp.json()

        # --- Bild extrahieren (inkl. DFC-Support) ---
        bild = _get_card_image(data)

        # --- Oracle-Text extrahieren ---
        oracle_text = _get_oracle_text(data)

        # --- Deutsche Übersetzung (Premium + KI) ---
        text_de = _translate_oracle_text(oracle_text, is_premium, benutzername)

        # --- Alle Prints/Auflagen laden ---
        prints = await _fetch_prints(client, data, bild)

        # --- Ergebnis zusammenbauen ---
        result = {
            "name": data.get("name"),
            "typ": data.get("type_line"),
            "text_de": text_de,
            "prints": prints,
        }
        scryfall_cache.set(cache_key, result)

        # --- Zusätzlich Card-Info im Einzel-Cache speichern ---
        _cache_individual_card(data, bild)

        return result


# ======================================================================
# GET /api/trends – Trending Cards / Markt-Trends
# ======================================================================
@router.get(
    "/trends",
    summary="Markt-Trends abrufen",
    description="Gibt personalisierte Trends (basierend auf der Sammlung) oder "
                "die teuersten Karten des neuesten Sets zurück.",
    response_model=TrendsResponse,
)
async def get_trends(
    current_user: str = Depends(get_current_user_optional),
):
    """
    Ablauf:
    1. Prüfen ob der User eine Sammlung hat → personalisierte Trends
    2. Fallback: Neuestes Set (Expansion/Core) → Top 5 teuerste Karten
    3. Notfall-Fallback: Statische Backup-Daten
    """
    # --- Personalisierte Trends ---
    benutzername = current_user or ""
    has_personalized = False
    if benutzername:
        async with get_db_session() as session:
            res = await session.execute(
                text(
                    "SELECT COUNT(*) as count FROM sammlung_alben "
                    "WHERE benutzername = :name "
                    "AND karten_name != '__PLACEHOLDER__' "
                    "AND album_name != 'Wunschliste'"
                ),
                {"name": benutzername},
            )
            row = res.mappings().first()
            if row and row["count"] > 0:
                has_personalized = True

    if has_personalized:
        return await _personalized_trends(benutzername)

    # --- Fallback: Neuestes Set ---
    return await _newest_set_trends()


# ======================================================================
# Private Hilfsfunktionen
# ======================================================================

def _get_card_image(data: dict) -> str:
    """Extrahiert die Bild-URL, unterstützt DFCs (doppelseitige Karten)."""
    bild = data.get("image_uris", {}).get("normal", "")
    if not bild and "card_faces" in data:
        bild = data["card_faces"][0].get("image_uris", {}).get("normal", "")
    return bild


def _get_oracle_text(data: dict) -> str:
    """Extrahiert den Oracle-Text, kombiniert DFC-Seiten mit //."""
    oracle_text = data.get("oracle_text", "")
    if not oracle_text and "card_faces" in data:
        oracle_text = "\n//\n".join(
            face.get("oracle_text", "") for face in data["card_faces"]
        )
    return oracle_text


def _translate_oracle_text(oracle_text: str, is_premium: bool, benutzername: str = "") -> str:
    """
    Übersetzt den Oracle-Text ins Deutsche.

    - Premium + KI verfügbar + Monatslimit nicht erreicht → Gemini-Übersetzung
    - Premium ohne KI (oder Limit erreicht) → Englischer Originaltext
    - Free → Paywall-Hinweis + Originaltext
    """
    if not oracle_text:
        return "Keine Textbeschreibung vorhanden."

    if is_premium and model_lite and check_and_increment_ai_usage(benutzername):
        try:
            prompt = (
                "Übersetze diesen Magic: The Gathering Kartentext möglichst akkurat "
                "ins Deutsche (benutze offizielle MTG-Terminologie wie 'Fliegend', "
                "'Tappen', 'Verursacht Trampelschaden', 'Erzeuge', etc.). "
                f"Antworte NUR mit dem übersetzten Text:\n{oracle_text}"
            )
            response = model_lite.generate_content(prompt)
            return response.text.strip()
        except Exception:
            return f"Originaltext (Englisch):\n{oracle_text}"
    elif not is_premium:
        return (
            "[Premium-Feature: Upgrade auf Grana Pro für deutsche Übersetzung]\n\n"
            f"Originaltext (Englisch):\n{oracle_text}"
        )
    else:
        return f"Originaltext (Englisch):\n{oracle_text}"


async def _fallback_lang_search(
    client: httpx.AsyncClient, search_term: str, original_resp
):
    """Sprachübergreifende Suche als Fallback (für deutsche Kartennamen)."""
    try:
        url_search = (
            f"https://api.scryfall.com/cards/search?"
            f"q=lang:any+name:%22{urllib.parse.quote(search_term)}%22"
        )
        search_resp = await client.get(url_search)
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            if "data" in search_data and len(search_data["data"]) > 0:
                english_name = search_data["data"][0]["name"]
                url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(english_name)}"
                return await client.get(url)
    except Exception:
        pass
    return original_resp


async def _fetch_prints(
    client: httpx.AsyncClient, data: dict, fallback_bild: str
) -> list:
    """Lädt alle Auflagen/Prints einer Karte von Scryfall."""
    prints = []
    prints_url = data.get("prints_search_uri")

    if prints_url:
        try:
            prints_resp = await client.get(prints_url)
            if prints_resp.status_code == 200:
                prints_data = prints_resp.json()
                for item in prints_data.get("data", []):
                    img_print = item.get("image_uris", {}).get("normal", "")
                    if not img_print and "card_faces" in item:
                        img_print = item["card_faces"][0].get("image_uris", {}).get("normal", "")

                    price_eur = (
                        item.get("prices", {}).get("eur")
                        or item.get("prices", {}).get("eur_foil")
                        or "0.00"
                    )
                    prints.append({
                        "set_name": item.get("set_name"),
                        "bild_url": img_print,
                        "preis": price_eur,
                    })
        except Exception:
            logger.exception("Error fetching prints")

    # Mindestens den aktuellen Print zurückgeben
    if not prints:
        prints = [{
            "set_name": data.get("set_name"),
            "bild_url": fallback_bild,
            "preis": data.get("prices", {}).get("eur", "0.00"),
        }]

    return prints


def _cache_individual_card(data: dict, bild: str) -> None:
    """Schreibt einen Einzel-Card-Eintrag in den Cache (für fetch_card_details_cached)."""
    card_info = {
        "name": data.get("name"),
        "image": bild,
        "type": data.get("type_line", ""),
        "cmc": data.get("cmc", 0.0),
        "colors": data.get("colors", []),
        "color_identity": data.get("color_identity", []),
        "prices": data.get("prices", {}),
        "price": data.get("prices", {}).get("eur", "0.00"),
        "legalities": data.get("legalities", {}),
    }
    card_name = data.get("name", "")
    if card_name:
        scryfall_cache.set(f"card:{card_name.lower().strip()}", card_info)


async def _personalized_trends(benutzername: str) -> dict:
    """Gibt die 5 neuesten Karten aus der Sammlung des Users als Trends zurück."""
    async with get_db_session() as session:
        res = await session.execute(
            text(
                "SELECT karten_name, bild_url, preis, album_name "
                "FROM sammlung_alben "
                "WHERE benutzername = :name "
                "AND karten_name != '__PLACEHOLDER__' "
                "AND album_name != 'Wunschliste' "
                "ORDER BY id DESC LIMIT 5"
            ),
            {"name": benutzername},
        )
        rows = res.mappings().all()

    # Live-Preise & Bilder von Scryfall holen
    unique_names = list(set(row["karten_name"] for row in rows))
    scryfall_data = await fetch_card_details_cached(unique_names)

    cards = []
    for r in rows:
        k_name = r["karten_name"]
        card_info = scryfall_data.get(k_name.lower().strip())
        live_p = card_info.get("price", r["preis"]) if card_info else r["preis"]
        live_img = card_info.get("image", r["bild_url"]) if card_info else r["bild_url"]
        cards.append({
            "id": k_name,
            "name": k_name,
            "image_uris": {"normal": live_img},
            "prices": {"eur": live_p},
            "album_name": r["album_name"],
        })

    return {"erfolg": True, "personalized": True, "data": cards}


async def _newest_set_trends() -> dict:
    """Fallback: Rotierende teure Karten des neuesten physischen Sets."""
    import random
    cache_key = "trends_newest_set_pool_15"
    pool = scryfall_cache.get(cache_key)

    if not pool:
        async with scryfall_client() as client:
            try:
                # 1. Neustes physisches Set ermitteln
                sets_resp = await client.get("https://api.scryfall.com/sets")
                if sets_resp.status_code == 200:
                    sets_data = sets_resp.json()
                    newest_set_code = None
                    for s in sets_data.get("data", []):
                        if s.get("set_type") in ["expansion", "core"] and not s.get("digital", False):
                            newest_set_code = s.get("code")
                            break

                    if newest_set_code:
                        # 2. Top 15 teuerste Karten aus diesem Set für Pool holen
                        search_url = (
                            f"https://api.scryfall.com/cards/search?"
                            f"q=set:{newest_set_code}+is:unique+not:digital+cheapest:eur"
                            f"&order=eur&dir=desc"
                        )
                        cards_resp = await client.get(search_url)
                        if cards_resp.status_code == 200:
                            cards_data = cards_resp.json()
                            raw_cards = cards_data.get("data", [])[:15]

                            pool = []
                            for c in raw_cards:
                                img = c.get("image_uris", {}).get("normal", "")
                                if not img and "card_faces" in c:
                                    img = c["card_faces"][0].get("image_uris", {}).get("normal", "")

                                price = (
                                    c.get("prices", {}).get("eur")
                                    or c.get("prices", {}).get("eur_foil")
                                    or "0.00"
                                )
                                pool.append({
                                    "id": c.get("id"),
                                    "name": c.get("name"),
                                    "image_uris": {"normal": img},
                                    "prices": {"eur": price},
                                    "set_name": c.get("set_name"),
                                })

                            scryfall_cache.set(cache_key, pool)
            except Exception:
                logger.exception("Error fetching newest set fallback trends")

    if pool:
        selected = random.sample(pool, min(len(pool), 5))
        return {"erfolg": True, "personalized": False, "data": selected}

    # --- Notfall-Backup: Rotierende statische Daten ---
    selected_static = random.sample(_STATIC_BACKUP_TRENDS, min(len(_STATIC_BACKUP_TRENDS), 5))
    return {"erfolg": True, "personalized": False, "data": selected_static}


# ======================================================================
# Statische Backup-Daten (falls Scryfall komplett down ist)
# ======================================================================
_STATIC_BACKUP_TRENDS = [
    {
        "id": "1",
        "name": "The One Ring",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/d/3/d3c1036b-4874-4beb-b7ea-0d9998ea401a.jpg"},
        "prices": {"eur": "80.00"},
    },
    {
        "id": "2",
        "name": "Sheoldred, the Apocalypse",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/d/6/d67be074-cdd4-41d9-ac89-0a0456c4e4b2.jpg"},
        "prices": {"eur": "65.00"},
    },
    {
        "id": "3",
        "name": "Orcish Bowmasters",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/7/c/7c024abd-237c-4efe-a28a-36ccd7f7a5b3.jpg"},
        "prices": {"eur": "38.00"},
    },
    {
        "id": "4",
        "name": "Mana Crypt",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/4/d/4d960186-4559-4af0-bd22-63bac17f8932.jpg"},
        "prices": {"eur": "180.00"},
    },
    {
        "id": "5",
        "name": "Ragavan, Nimble Pilferer",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/a/9/a9738cda-adb1-47fb-9f4c-ecd930228c4d.jpg"},
        "prices": {"eur": "35.00"},
    },
    {
        "id": "6",
        "name": "Jeweled Lotus",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/3/c/3c7f8f4c-2400-47b2-bc18-acdfd8e7e174.jpg"},
        "prices": {"eur": "75.00"},
    },
    {
        "id": "7",
        "name": "Chrome Mox",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/f/3/f340cd0d-7ed6-4654-bf63-cbf1dcf87869.jpg"},
        "prices": {"eur": "82.00"},
    },
    {
        "id": "8",
        "name": "Black Lotus",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/b/d/bd13b2d1-c114-411a-8bb7-d7795bd7e810.jpg"},
        "prices": {"eur": "15000.00"},
    },
    {
        "id": "9",
        "name": "Mox Diamond",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/e/2/e29124b4-dd4c-47bc-8a71-6c2e399c0490.jpg"},
        "prices": {"eur": "550.00"},
    },
    {
        "id": "10",
        "name": "Gaea's Cradle",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/2/5/25b0b816-0583-44aa-9dc5-f3ff48993a51.jpg"},
        "prices": {"eur": "850.00"},
    },
    {
        "id": "11",
        "name": "Sol Ring",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/1/1/117c7c87-ec92-46cd-a24f-0de53fc0f04e.jpg"},
        "prices": {"eur": "1.50"},
    },
    {
        "id": "12",
        "name": "Cyclonic Rift",
        "image_uris": {"normal": "https://cards.scryfall.io/normal/front/9/1/917bb54a-4a40-4221-995a-c51e813a30ff.jpg"},
        "prices": {"eur": "32.00"},
    },
]


# ======================================================================
# Request Model & Endpoint für Affiliate Klick-Tracking
# ======================================================================
class AffiliateTrackReq(BaseModel):
    card_name: str
    set_name: Optional[str] = None
    price: Optional[str] = None

@router.post(
    "/v1/affiliate/track",
    summary="Affiliate-Klick tracken",
)
async def track_affiliate_click(req: AffiliateTrackReq):
    """
    Loggt den Klick auf den Cardmarket-Affiliate-Link im Serverlog.
    """
    logger.info(
        "[AFFILIATE CLICK] Karte: %s, Edition: %s, Preis: %s EUR",
        req.card_name, req.set_name or "Unbekannt", req.price or "0.00",
    )
    return {"erfolg": True}

