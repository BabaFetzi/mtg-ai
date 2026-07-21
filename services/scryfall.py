"""
services/scryfall.py – Scryfall API-Client & Karten-Hilfsfunktionen

Kapselt alle Interaktionen mit der Scryfall API:
- fetch_card_details_cached(): Batch-Fetch für Kartenlisten mit Cache
- clean_card_name(): Bereinigt Kartennamen (Foil-Tags, Set-Codes, etc.)
- parse_decklist(): Parst Decklisten-Strings in strukturierte Daten
"""

import asyncio
import logging
import re
import urllib.parse
from typing import List, Dict, Any

import httpx

from services.cache import scryfall_cache

logger = logging.getLogger(__name__)

# ======================================================================
# Scryfall-Client-Konfiguration
# ----------------------------------------------------------------------
# Scryfall verlangt einen aussagekräftigen `User-Agent` und einen
# `Accept`-Header. Fehlen sie, drosselt oder blockt die API die Anfragen
# (HTTP 429/403). Ausserdem bittet Scryfall um max. ~10 Anfragen/Sekunde --
# deshalb eine kleine Pause zwischen den Einzelabrufen im Fallback-Loop.
# ======================================================================
SCRYFALL_HEADERS = {
    "User-Agent": "GranaMTG/1.0 (+https://github.com/BabaFetzi/mtg-ai)",
    "Accept": "application/json",
}
SCRYFALL_MIN_DELAY = 0.1  # Sekunden Pause zwischen Einzelabrufen


def scryfall_client(**kwargs) -> httpx.AsyncClient:
    """httpx-Client mit dem von Scryfall geforderten User-Agent/Accept-Header."""
    kwargs.setdefault("headers", SCRYFALL_HEADERS)
    kwargs.setdefault("timeout", 20.0)
    return httpx.AsyncClient(**kwargs)


async def scryfall_request(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> httpx.Response:
    """
    Führt eine Scryfall-Anfrage aus und wiederholt sie EINMAL bei HTTP 429
    (Rate-Limit), wobei der `Retry-After`-Header respektiert wird (max. 5s).
    Verhindert, dass eine kurzzeitige Drosselung sofort als "nicht gefunden"
    durchschlägt.
    """
    resp = await client.request(method, url, **kwargs)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        try:
            wait = min(float(retry_after), 5.0) if retry_after else 1.0
        except (TypeError, ValueError):
            wait = 1.0
        logger.warning("Scryfall Rate-Limit (429). Warte %.1fs und versuche erneut.", wait)
        await asyncio.sleep(wait)
        resp = await client.request(method, url, **kwargs)
    return resp


# ======================================================================
# Hilfsfunktionen
# ======================================================================

def clean_card_name(name: str) -> str:
    """
    Bereinigt einen Kartennamen für die Scryfall-Suche.

    Entfernt:
    - Foil-Tags (*F*, *Foil*, foil)
    - Klammern mit Inhalt am Ende ((Commander), [Showcase], etc.)
    - Standard Set-Codes ((ELD) 123, [MH2])
    - Trailing Nummern
    - Nimmt bei DFCs (doppelseitigen Karten) nur die Vorderseite
    """
    # Foil-Tags entfernen
    name = re.sub(r'\*[fF](oil)?\*', '', name)
    name = re.sub(r'(?i)\bfoil\b', '', name)

    # Klammern am Ende iterativ entfernen
    while True:
        new_name = re.sub(r'\s*\([^)]+\)\s*$', '', name)
        new_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', new_name)
        if new_name == name:
            break
        name = new_name

    # Set-Codes / Collector Numbers
    name = re.sub(r'\([a-zA-Z0-9]{3,4}\)\s*\d*', '', name)
    name = re.sub(r'\([a-zA-Z0-9]{3,4}\)', '', name)
    name = re.sub(r'\[[a-zA-Z0-9]{3,4}\]\s*\d*', '', name)
    name = re.sub(r'\[[a-zA-Z0-9]{3,4}\]', '', name)

    # Trailing Ziffern
    name = re.sub(r'\s+\d+$', '', name)

    # DFC: Nur Vorderseite verwenden
    if "//" in name:
        name = name.split("//")[0].strip()

    return re.sub(r'\s+', ' ', name).strip()


def parse_decklist(deck_liste: str) -> List[Dict[str, Any]]:
    """
    Parst eine Deckliste im Format "1x Sol Ring" oder "1 Sol Ring".

    Ignoriert Kommentare (#, //) und Kategorie-Header (Zeilen die mit : enden).
    Gibt eine Liste von Dicts mit 'count' und 'name' zurück.
    """
    lines = deck_liste.strip().split('\n')
    parsed = []
    metadata_headers = {"deck", "commander", "companion", "sideboard", "mainboard", "main"}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Kommentare und Kategorie-Header überspringen
        if line.startswith('#') or line.startswith('//') or line.lower().endswith(':'):
            continue
        if line.lower() in metadata_headers:
            continue
        match = re.match(r'^(\d+)[xX]?\s+(.+)$', line)
        if match:
            parsed.append({
                "count": int(match.group(1)),
                "name": clean_card_name(match.group(2).strip()),
            })
        else:
            parsed.append({"count": 1, "name": clean_card_name(line)})
    return parsed


def _extract_card_info(card_data: dict) -> Dict[str, Any]:
    """Extrahiert ein normalisiertes Card-Info-Dict aus einem Scryfall-Datenobjekt."""
    img = card_data.get("image_uris", {}).get("normal", "")
    if not img and "card_faces" in card_data:
        img = card_data["card_faces"][0].get("image_uris", {}).get("normal", "")

    price_val = (
        card_data.get("prices", {}).get("eur")
        or card_data.get("prices", {}).get("eur_foil")
        or "0.00"
    )

    return {
        "name": card_data["name"],
        "image": img,
        "type": card_data.get("type_line", ""),
        "cmc": card_data.get("cmc", 0.0),
        "colors": card_data.get("colors", []),
        "color_identity": card_data.get("color_identity", []),
        "prices": card_data.get("prices", {}),
        "price": price_val,
        "legalities": card_data.get("legalities", {}),
    }


def _cache_card_info(card_info: Dict[str, Any], *extra_keys: str) -> None:
    """Schreibt card_info unter dem kanonischen Namen und optionalen Extra-Keys in den Cache."""
    canonical_key = f"card:{card_info['name'].lower().strip()}"
    scryfall_cache.set(canonical_key, card_info)

    # DFC: Auch die Vorderseite separat cachen
    if "//" in card_info["name"]:
        front_face = card_info["name"].split("//")[0].strip().lower()
        scryfall_cache.set(f"card:{front_face}", card_info)

    # Weitere Keys (z.B. Original-Eingabe)
    for key in extra_keys:
        if key:
            scryfall_cache.set(f"card:{key.lower().strip()}", card_info)


# ======================================================================
# Haupt-Funktion: Batch-Fetch mit Cache
# ======================================================================

async def fetch_card_details_cached(names: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Löst eine Liste von Kartennamen zu Scryfall-Daten auf.

    1. Prüft den Cache für jeden Namen
    2. Holt nicht-gecachte Karten via POST /cards/collection (max 75 pro Batch)
    3. Fallback: Fuzzy-Suche für nicht gefundene Karten
    4. Fallback 2: Sprachübergreifende Suche (für deutsche Namen)

    Returns:
        Dict[str, CardInfo] – Mapping von name.lower().strip() → Card-Info
    """
    scryfall_data: Dict[str, Dict[str, Any]] = {}
    uncached_names: List[str] = []

    # --- Phase 1: Cache-Lookup ---
    for name in names:
        cache_key = f"card:{name.lower().strip()}"
        cached = scryfall_cache.get(cache_key)
        if cached:
            scryfall_data[name.lower().strip()] = cached
        else:
            # DFC: Auch unter dem Vorderseiten-Namen suchen
            front_key = name
            if "//" in name:
                front_key = name.split("//")[0].strip()
            cached_front = scryfall_cache.get(f"card:{front_key.lower().strip()}")
            if cached_front:
                scryfall_data[name.lower().strip()] = cached_front
                scryfall_data[front_key.lower().strip()] = cached_front
            else:
                uncached_names.append(name)

    if not uncached_names:
        return scryfall_data

    # --- Phase 2: Batch-Fetch via /cards/collection ---
    async with scryfall_client() as client:
        for i in range(0, len(uncached_names), 75):
            name_mapping: Dict[str, str] = {}  # cleaned_lower → original_input
            chunk: List[Dict[str, str]] = []

            for n in uncached_names[i : i + 75]:
                query_name = n
                if "//" in n:
                    query_name = n.split("//")[0].strip()
                query_name_clean = clean_card_name(query_name)
                if query_name_clean:
                    name_mapping[query_name_clean.lower().strip()] = n
                    chunk.append({"name": query_name_clean})

            if not chunk:
                continue

            try:
                resp = await scryfall_request(
                    client,
                    "POST",
                    "https://api.scryfall.com/cards/collection",
                    json={"identifiers": chunk},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for c in data.get("data", []):
                        card_info = _extract_card_info(c)
                        c_name_lower = c["name"].lower().strip()

                        # In Cache schreiben + Ergebnis-Dict befüllen
                        _cache_card_info(card_info)
                        scryfall_data[c_name_lower] = card_info

                        # DFC-Mapping
                        if "//" in c["name"]:
                            front_face = c["name"].split("//")[0].strip().lower()
                            scryfall_data[front_face] = card_info

                        # Original-Input-Name zuordnen
                        for q_clean, orig_n in name_mapping.items():
                            if q_clean == c_name_lower or (
                                "//" in c["name"]
                                and q_clean == c["name"].split("//")[0].strip().lower()
                            ):
                                _cache_card_info(card_info, orig_n)
                                scryfall_data[orig_n.lower().strip()] = card_info
            except Exception:
                logger.exception("Error in collection fetch")

            # --- Phase 3: Fallbacks für nicht aufgelöste Namen ---
            for identifier in chunk:
                input_name = identifier["name"]
                input_name_lower = input_name.lower().strip()
                orig_n = name_mapping.get(input_name_lower, input_name)
                orig_n_lower = orig_n.lower().strip()

                if orig_n_lower in scryfall_data:
                    continue  # Bereits gefunden

                # Kleine Pause vor jedem Einzelabruf, um Scryfalls Rate-Limit
                # (~10 Anfragen/Sekunde) auch bei grossen Importen einzuhalten.
                await asyncio.sleep(SCRYFALL_MIN_DELAY)

                # Fallback 1: Fuzzy-Suche (Tippfehler, fehlende Satzzeichen)
                card_info = await _fallback_fuzzy(client, input_name)
                if card_info:
                    _cache_card_info(card_info, orig_n_lower, input_name_lower)
                    scryfall_data[orig_n_lower] = card_info
                    scryfall_data[input_name_lower] = card_info
                    scryfall_data[card_info["name"].lower().strip()] = card_info
                    continue

                # Fallback 2: Sprachübergreifende Suche (deutsche Namen)
                card_info = await _fallback_multilang(client, input_name)
                if card_info:
                    _cache_card_info(card_info, orig_n_lower, input_name_lower)
                    scryfall_data[orig_n_lower] = card_info
                    scryfall_data[input_name_lower] = card_info
                    scryfall_data[card_info["name"].lower().strip()] = card_info

    return scryfall_data


# ======================================================================
# Fallback-Suchen (Privat)
# ======================================================================

async def _fallback_fuzzy(
    client: httpx.AsyncClient, card_name: str
) -> Dict[str, Any] | None:
    """Versucht eine Fuzzy-Suche über Scryfall /cards/named?fuzzy=..."""
    try:
        url = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(card_name)}"
        resp = await scryfall_request(client, "GET", url)
        if resp.status_code == 200:
            return _extract_card_info(resp.json())
    except Exception:
        pass
    return None


async def _fallback_multilang(
    client: httpx.AsyncClient, card_name: str
) -> Dict[str, Any] | None:
    """Sucht sprachübergreifend (ideal für deutsche Kartennamen)."""
    try:
        url = (
            f"https://api.scryfall.com/cards/search?"
            f"q=lang:any+name:%22{urllib.parse.quote(card_name)}%22"
        )
        resp = await scryfall_request(client, "GET", url)
        if resp.status_code == 200:
            search_data = resp.json()
            if "data" in search_data and len(search_data["data"]) > 0:
                return _extract_card_info(search_data["data"][0])
    except Exception:
        pass
    return None
