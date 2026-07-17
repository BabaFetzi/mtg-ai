import httpx
import logging
import time
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# Simple in-memory cache with 24h TTL
# Format: { format_name: (set_of_banned_cards, expiration_timestamp) }
banned_cache: Dict[str, tuple[Set[str], float]] = {}
restricted_cache: Dict[str, tuple[Set[str], float]] = {}

CACHE_TTL = 86400  # 24 hours

async def fetch_banned_cards(format_name: str) -> Set[str]:
    now = time.time()
    if format_name in banned_cache:
        banned, expires = banned_cache[format_name]
        if now < expires:
            return banned

    banned_set = set()
    try:
        # Scryfall search query: banned in this format
        url = f"https://api.scryfall.com/cards/search?q=banned:{format_name}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                for card in data.get("data", []):
                    banned_set.add(card["name"].lower())
                # Handle pagination if any (usually banned lists fit in 175 cards, but let's be safe)
                while data.get("has_more", False):
                    next_page = data.get("next_page")
                    if next_page:
                        response = await client.get(next_page)
                        if response.status_code == 200:
                            data = response.json()
                            for card in data.get("data", []):
                                banned_set.add(card["name"].lower())
                        else:
                            break
                    else:
                        break
    except Exception:
        logger.exception("Error fetching banned cards for format %s from Scryfall", format_name)
        # Fallback to empty if Scryfall offline, or keep old cache if available
        if format_name in banned_cache:
            return banned_cache[format_name][0]
            
    banned_cache[format_name] = (banned_set, now + CACHE_TTL)
    return banned_set

async def fetch_restricted_cards(format_name: str) -> Set[str]:
    if format_name != "vintage":
        return set()
        
    now = time.time()
    if format_name in restricted_cache:
        restricted, expires = restricted_cache[format_name]
        if now < expires:
            return restricted

    restricted_set = set()
    try:
        url = f"https://api.scryfall.com/cards/search?q=restricted:{format_name}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                for card in data.get("data", []):
                    restricted_set.add(card["name"].lower())
    except Exception:
        logger.exception("Error fetching restricted cards for format %s", format_name)
        if format_name in restricted_cache:
            return restricted_cache[format_name][0]

    restricted_cache[format_name] = (restricted_set, now + CACHE_TTL)
    return restricted_set
