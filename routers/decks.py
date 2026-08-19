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

import asyncio
import hashlib
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session, check_user_premium
from services.cache import scryfall_cache
from services.scryfall import (fetch_card_details_cached, clean_card_name, parse_decklist,
                               build_deck_card_facts, drucke_fuer_deck, druck_zu_eintrag)
from services.deckliste import auflage_setzen, karte_entfernen, karte_hinzufuegen
from services.ai_service import model, model_lite, modell_fuer
from services.bestand import abgleichen, bedarf_aus_deck, bestand_aus_zeilen
from services.manabasis import analysiere as analysiere_manabasis
from services.limiter import limiter
from services.usage_limiter import check_and_increment_ai_usage, gutschreiben
from format_engine import BASIC_LANDS, FormatValidator
from schemas.models import (
    DeckErstellenReq,
    DeckUpdateReq,
    DeckLoeschenReq,
    DeckAnalyseReq,
    ValidateDeckReq
)

logger = logging.getLogger(__name__)

# Warum 120 pro Minute und nicht 30: ein einziger Blick auf "Analyse & Stats"
# löst fünf dieser Aufrufe gleichzeitig aus (Statistik, Wert, Regelcheck,
# Farbquellen, Sammlungsabgleich). Mit 30 war nach sechs Deckansichten pro
# Minute Schluss -- im Lasttest die häufigste Fehlerursache. Gezählt wird seit
# services/limiter.py pro angemeldetem Nutzer, nicht mehr pro Adresse; damit
# ist eine höhere Zahl auch vertretbar.

# ======================================================================
# Lokale Request-Modelle für Add/Remove (zur API-Kompatibilität)
# ======================================================================
class AuflageFelder(BaseModel):
    """Welche Auflage gemeint ist -- optional.

    Fehlt sie, verhalten sich die Endpunkte wie bisher: sie greifen die erste
    Zeile mit diesem Kartennamen, gleich aus welchem Set. Steht sie dabei, ist
    genau diese Auflage gemeint.

    Die Längen sind eng gefasst, weil beides direkt in die Deckliste des Nutzers
    geschrieben wird: Set-Codes haben bei Scryfall höchstens sechs Zeichen,
    Sammlernummern höchstens zwölf.
    """
    set: Optional[str] = Field(default=None, max_length=6)
    sammlernummer: Optional[str] = Field(default=None, max_length=12)


class DeckAddCardReq(AuflageFelder):
    deck_id: int
    card_name: str = Field(max_length=200)

class DeckRemoveCardReq(AuflageFelder):
    deck_id: int
    card_name: str = Field(max_length=200)

class DeckAuflageReq(AuflageFelder):
    """Auflage einer Karte im Deck wechseln.

    'set'/'sammlernummer' sind die NEUE Auflage (leer = wieder ohne Festlegung),
    'alt_set'/'alt_sammlernummer' benennen die Zeile, die gemeint ist -- nötig,
    wenn dieselbe Karte in mehreren Auflagen im Deck steht.
    """
    deck_id: int
    card_name: str = Field(max_length=200)
    alt_set: Optional[str] = Field(default=None, max_length=6)
    alt_sammlernummer: Optional[str] = Field(default=None, max_length=12)

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
def _serialize_dt(value):
    """SQLite liefert Timestamps über raw SQL als String, PostgreSQL/asyncpg
    als echtes datetime-Objekt -- vereinheitlicht für die JSON-Antwort."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.get(
    "/decks/{benutzername}",
    summary="Decks eines Benutzers abrufen",
)
async def get_decks(benutzername: str, current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Decks dieses Benutzers.")
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM decks WHERE benutzername = :name"),
                {"name": current_user}
            )
            rows = res.mappings().all()

        # Für die Deck-Bibliothek-Karten (Kartenzahl, Farbidentität, Mini-Kurve,
        # Preis) reicht das rohe id/name/liste/format nicht mehr. Alle Karten-
        # namen über ALLE Decks hinweg werden zusammen aufgelöst, statt pro Deck
        # einzeln -- ein Cache-/Batch-Durchlauf statt N, da Karten wie Sol Ring
        # oder Command Tower ohnehin oft in mehreren Decks vorkommen.
        parsed_per_deck = {r["id"]: parse_decklist(r["liste"] or "") for r in rows}
        alle_namen = {p["name"] for parsed in parsed_per_deck.values() for p in parsed}
        scryfall_data = await fetch_card_details_cached(list(alle_namen)) if alle_namen else {}

        decks = []
        for r in rows:
            parsed = parsed_per_deck[r["id"]]
            # Nur das Hauptdeck: die Anzeige "x / 60+" bzw. "x / 100" vergleicht
            # gegen die Formatvorgabe, und dort zählt das Sideboard nicht mit.
            card_count = sum(p["count"] for p in parsed if not p.get("sideboard"))
            sideboard_count = sum(p["count"] for p in parsed if p.get("sideboard"))
            color_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
            cmc_curve = {}
            gesamt_preis = 0.0

            for p in parsed:
                info = scryfall_data.get(p["name"].lower().strip())
                if not info:
                    continue
                count = p["count"]
                type_line = info.get("type", "")

                if "Land" not in type_line:
                    try:
                        cmc = int(float(info.get("cmc") or 0.0))
                    except (ValueError, TypeError):
                        cmc = 0
                    cmc_curve[str(cmc)] = cmc_curve.get(str(cmc), 0) + count

                for color in set(info.get("colors", []) or []):
                    if color in color_counts:
                        color_counts[color] += count

                try:
                    preis = float(info.get("price") or 0.0)
                except (ValueError, TypeError):
                    preis = 0.0
                gesamt_preis += preis * count

            decks.append({
                "id": r["id"],
                "name": r["name"],
                "liste": r["liste"],
                "format": r.get("format") or "commander",
                "card_count": card_count,
                "sideboard_count": sideboard_count,
                "colors": color_counts,
                "cmc_curve": cmc_curve,
                "price": f"{gesamt_preis:.2f}",
                "updated_at": _serialize_dt(r.get("aktualisiert_am")),
            })
        return decks
    except HTTPException:
        raise
    except Exception:
        logger.exception("Fehler beim Laden der Decks für %s", current_user)
        raise HTTPException(status_code=500, detail="Interner Serverfehler beim Laden der Decks.")

# ======================================================================
# POST /api/decks/erstellen – Deck erstellen
# ======================================================================
@router.post(
    "/decks/erstellen",
    summary="Neues Deck erstellen",
)
async def create_deck(data: DeckErstellenReq, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        is_premium = await check_user_premium(current_user)
        if not is_premium:
            res = await session.execute(
                text("SELECT COUNT(*) FROM decks WHERE benutzername = :name"),
                {"name": current_user}
            )
            count = res.scalar()
            if count >= 3:
                raise HTTPException(
                    status_code=403,
                    detail="Limit erreicht: Kostenlose Konten können maximal 3 Decks erstellen. Bitte erwerbe Grana Pro für unbegrenzte Decks."
                )

        # erstellt_am/aktualisiert_am müssen hier explizit gesetzt werden --
        # die ORM-Column-Defaults (Deck.erstellt_am/aktualisiert_am in
        # database.py) feuern nur bei session.add(), nicht bei rohem SQL wie
        # hier, sonst bleiben beide Spalten dauerhaft NULL.
        await session.execute(
            text(
                "INSERT INTO decks (benutzername, name, liste, format, erstellt_am, aktualisiert_am) "
                "VALUES (:user, :name, :list, :format, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"user": current_user, "name": data.deck_name, "list": data.deck_liste, "format": data.format or "commander"}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/decks/update – Deckliste aktualisieren
# ======================================================================
@router.post(
    "/decks/update",
    summary="Deck aktualisieren",
)
async def update_deck(data: DeckUpdateReq, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT benutzername FROM decks WHERE id = :id"),
            {"id": data.deck_id}
        )
        row = res.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Deck nicht gefunden.")
        if row["benutzername"] != current_user:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Deck.")

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
            update_parts.append("aktualisiert_am = CURRENT_TIMESTAMP")
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
async def delete_deck(data: DeckLoeschenReq, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM decks WHERE id = :id AND benutzername = :user"),
            {"id": data.deck_id, "user": current_user}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/deck/visualize – Visualisierung der Kartenbilder
# ======================================================================
@router.post(
    "/deck/visualize",
    summary="Kartenbilder für Deck auflösen",
)
@limiter.limit("120/minute")
async def deck_visualize(req: DeckAnalyseReq, request: Request, current_user: str = Depends(get_current_user)):
    parsed = parse_decklist(req.deck_liste)
    if not parsed:
        return {"karten": []}
    
    unique_names = list(set([p["name"] for p in parsed]))
    scryfall_data = await fetch_card_details_cached(unique_names)
    # Die in der Deckliste genannten Auflagen ("(2XM) 123") auflösen. Ohne das
    # zeigte die Ansicht immer den Standarddruck -- also ein anderes Bild und
    # einen anderen Preis als die Karte, die tatsächlich im Deck steckt.
    drucke = await drucke_fuer_deck(parsed)

    karten = []
    for p in parsed:
        name_lower = p["name"].lower().strip()
        druck = druck_zu_eintrag(p, drucke)
        # 'auflage_gewuenscht' sagt, dass eine Auflage in der Liste STEHT --
        # 'auflage_gefunden', ob sie sich auflösen liess. Beides getrennt zu
        # melden ist der Unterschied zwischen "keine Auflage gewählt" und
        # "gewählte Auflage nicht auffindbar"; die Oberfläche darf das nicht
        # verwechseln und dem Nutzer den Standarddruck als seine Wahl zeigen.
        auflage = {
            "set": (druck or {}).get("set") or p.get("set"),
            "set_name": (druck or {}).get("set_name", ""),
            "sammlernummer": (druck or {}).get("sammlernummer") or p.get("sammlernummer"),
            "auflage_gewuenscht": bool(p.get("set")),
            "auflage_gefunden": druck is not None,
        }
        if name_lower in scryfall_data:
            basis = scryfall_data[name_lower]
            karten.append({
                "count": p["count"],
                "name": basis["name"],
                "image": (druck or {}).get("image") or basis["image"],
                "type": basis["type"],
                "cmc": basis.get("cmc", 0),
                "price": (druck or {}).get("price") or basis.get("price", "0.00"),
                # Der Starthand-Simulator baut seine Bibliothek aus dieser
                # Liste. Ohne die Kennzeichnung mischte er Sideboard-Karten
                # mit ein -- aus dem Sideboard zieht man aber nie.
                "sideboard": bool(p.get("sideboard")),
                **auflage,
            })
        else:
            karten.append({
                "count": p["count"],
                "name": p["name"] + " (Nicht gefunden)",
                "image": "",
                "type": "Unbekannt",
                "cmc": 0,
                "price": "0.00",
                "sideboard": bool(p.get("sideboard")),
                **auflage,
            })

    return {"karten": karten}

# ======================================================================
# POST /api/deck/stats – CMC-Kurve und Farben berechnen
# ======================================================================
@router.post(
    "/deck/stats",
    summary="Statistiken berechnen",
)
@limiter.limit("120/minute")
async def deck_stats(req: DeckAnalyseReq, request: Request, current_user: str = Depends(get_current_user)):
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
# POST /api/deck/manabasis – Farbquellen gegen Farbbedarf
# ======================================================================
@router.post(
    "/deck/manabasis",
    summary="Farbquellen prüfen",
)
@limiter.limit("120/minute")
async def deck_manabasis(req: DeckAnalyseReq, request: Request, current_user: str = Depends(get_current_user)):
    """Prüft, ob die Länder zu den Farbanforderungen des Decks passen.

    Sideboard-Karten bleiben aussen vor: gerechnet wird die Starthand des
    Hauptdecks.
    """
    parsed = [p for p in parse_decklist(req.deck_liste) if not p.get("sideboard")]
    unique_names = list({p["name"] for p in parsed})
    scryfall_data = await fetch_card_details_cached(unique_names)

    karten = []
    unbekannt = []
    for p in parsed:
        info = scryfall_data.get(p["name"].lower().strip())
        if info:
            karten.append((p["count"], info))
        else:
            unbekannt.append(p["name"])

    ergebnis = analysiere_manabasis(karten)
    # Ehrlich benennen, worauf die Rechnung beruht: unbekannte Karten fehlen
    # in der Deckgrösse und verschieben damit jede Wahrscheinlichkeit.
    ergebnis["nicht_gefunden"] = sorted(set(unbekannt))[:20]
    return ergebnis


async def bestand_des_nutzers(benutzer: str) -> Dict[str, int]:
    """Kartenbestand eines Nutzers als {vergleichsname: stueckzahl}.

    COUNT, nicht SUM(anzahl): jede Zeile ist genau ein physisches Exemplar,
    die Spalte `anzahl` wird von den Inserts nie gefüllt.
    """
    async with get_db_session() as session:
        res = await session.execute(
            text(
                "SELECT karten_name, COUNT(*) AS anzahl FROM sammlung_alben "
                "WHERE benutzername = :user AND karten_name != '__PLACEHOLDER__' "
                "GROUP BY karten_name"
            ),
            {"user": benutzer},
        )
        return bestand_aus_zeilen(res.mappings().all())


# ======================================================================
# POST /api/deck/abgleich – Was aus dem Deck liegt schon in der Sammlung?
# ======================================================================
@router.post(
    "/deck/abgleich",
    summary="Deck mit der eigenen Sammlung abgleichen",
)
@limiter.limit("120/minute")
async def deck_abgleich(req: DeckAnalyseReq, request: Request, current_user: str = Depends(get_current_user)):
    """Vergleicht die Deckliste mit der Sammlung des angemeldeten Nutzers.

    Beantwortet die Frage, die sich bei jedem neuen Deck stellt: was davon habe
    ich schon, was muss ich noch besorgen und was kostet das?

    Die eigentliche Rechnung steht in services/bestand.py -- dieselbe, die auch
    die Übernahme in die Sammlung benutzt. Liefen beide auseinander, würde der
    Knopf etwas anderes hinzufügen, als danebensteht.
    """
    parsed = parse_decklist(req.deck_liste)
    if not parsed:
        return {"karten": [], "benoetigt": 0, "vorhanden": 0, "fehlend": 0,
                "fehlender_wert": "0.00", "standardlaender_fehlend": 0}

    bestand = await bestand_des_nutzers(current_user)
    scryfall_data = await fetch_card_details_cached(list({p["name"] for p in parsed}))
    # Mit den Auflagen: sonst stünden auf derselben Seite zwei verschieden
    # gerechnete Beträge -- Deckwert mit der gewählten Auflage, Fehlbetrag mit
    # dem Standarddruck.
    drucke = await drucke_fuer_deck(parsed)
    return abgleichen(bedarf_aus_deck(parsed, scryfall_data, drucke), bestand)


# ======================================================================
# POST /api/deck/wert – Gesamtwert des Decks
# ======================================================================
@router.post(
    "/deck/wert",
    summary="Deckwert berechnen",
)
@limiter.limit("120/minute")
async def deck_wert(req: DeckAnalyseReq, request: Request, current_user: str = Depends(get_current_user)):
    """Gesamtwert der Deckliste.

    Rechnet mit der AUFLAGE, die in der Liste steht. Das ist der eigentliche
    Grund, warum die Auflage überhaupt gespeichert wird: derselbe Kartenname
    kostet je nach Druck 30 Cent oder 300 Euro. Ohne Auflage in der Zeile gilt
    weiterhin der Standarddruck.
    """
    parsed = parse_decklist(req.deck_liste)
    unique_names = list(set([p["name"] for p in parsed]))
    total_value = 0.0

    scryfall_data = await fetch_card_details_cached(unique_names)
    drucke = await drucke_fuer_deck(parsed)
    for p in parsed:
        name_lower = p["name"].lower().strip()
        c = druck_zu_eintrag(p, drucke) or scryfall_data.get(name_lower)
        if not c:
            continue
        count = p["count"]
        try:
            price = float(c.get("price") or 0.0)
        except (ValueError, TypeError):
            price = 0.0
        total_value += (price * count)

    return {"gesamt_wert": f"{total_value:.2f}"}

# ======================================================================
# Kartenerdung für die KI-Deck-Funktionen
# ======================================================================
async def _deck_fakten(deck_liste: str):
    """Holt bestätigte Kartendaten zur Deckliste.

    Die Erdung ist eine Verbesserung, kein Muss: Fällt Scryfall aus, läuft die
    Analyse weiter -- nur ohne Faktenblock, statt komplett zu scheitern.
    """
    try:
        return await build_deck_card_facts(deck_liste)
    except Exception:
        logger.warning("Kartenerdung für Deck-Funktion fehlgeschlagen", exc_info=True)
        return "", []


def _fakten_abschnitt(fakten: str, nicht_gefunden: list) -> str:
    """Baut den Prompt-Abschnitt mit den bestätigten Kartendaten."""
    if not fakten and not nicht_gefunden:
        return ""
    teile = [
        "WICHTIG: Stütze dich bei Kartenfähigkeiten AUSSCHLIESSLICH auf die folgenden "
        "bestätigten Kartendaten. Erfinde keine Kartentexte.",
    ]
    if fakten:
        teile.append("\nBESTÄTIGTE KARTENDATEN (live von Scryfall):\n" + fakten)
    if nicht_gefunden:
        teile.append(
            "\nNICHT AUFLÖSBAR (keine Aussagen zu deren Fähigkeiten treffen): "
            + ", ".join(nicht_gefunden)
        )
    return "\n".join(teile) + "\n\n"


# ======================================================================
# POST /api/deck/analyse – KI-gestützte Deck-Analyse (Premium)
# ======================================================================
@router.post(
    "/deck/analyse",
    summary="KI-Deck-Analyse",
)
async def deck_analyse(req: DeckAnalyseReq, current_user: str = Depends(get_current_user)):
    is_premium = await check_user_premium(current_user)
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

    if modell_fuer("deck_analyse") and await check_and_increment_ai_usage(current_user):
        try:
            # Echte Kartendaten beschaffen. Ohne sie musste das Modell jeden
            # Kartentext aus dem Gedächtnis rekonstruieren und hat ihn bei
            # unbekannten Karten erfunden.
            fakten, nicht_gefunden = await _deck_fakten(req.deck_liste)
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
                + _fakten_abschnitt(fakten, nicht_gefunden)
                + f"Deckliste:\n{req.deck_liste}"
            )
            # In einem Thread: der Gemini-Aufruf ist synchron und dauert Sekunden --
            # direkt im Endpunkt blockierte er den Event-Loop und damit ALLE
            # anderen gleichzeitigen Anfragen.
            response = await asyncio.to_thread(
                modell_fuer("deck_analyse").generate_content, prompt, None,
                "deck_analyse", current_user
            )
            text_resp = response.text
            match = re.search(r'\{.*\}', text_resp, re.DOTALL)
            if match:
                text_resp = match.group(0)
            
            result = json.loads(text_resp)
            scryfall_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.exception("Error generating deck analysis")
            # Der Aufruf wurde gezaehlt, hat aber nie geantwortet -- sonst
            # verbraucht ein zahlender Kunde sein Monatskontingent fuer
            # lauter Fehlermeldungen.
            await gutschreiben(current_user)
            
    fallback_res = {
        # Kein Ersatz-Ergebnis erfinden: Ohne KI-Antwort gibt es KEINE Bewertung.
        # Vorher standen hier überall "score: 5" und "power_level: 5" -- im
        # Frontend sah das aus wie eine echte Analyse, war aber geraten.
        "nicht_verfuegbar": True,
        "strategie": "Die KI-Analyse ist momentan nicht verfügbar. Bitte versuche es später erneut.",
        "commander": None,
        "staerken": [],
        "schwaechen": {},
        "synergien": [],
        "combos": [],
        "verbesserungen": [],
        "format_kontext": None,
        "power_level": None
    }
    return fallback_res

# ======================================================================
# POST /api/deck/roast – Deck-Roast (Premium)
# ======================================================================
@router.post(
    "/deck/roast",
    summary="Humorvoller Deck-Roast",
)
async def deck_roast(req: DeckAnalyseReq, current_user: str = Depends(get_current_user)):
    is_premium = await check_user_premium(current_user)
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

    if modell_fuer("deck_roast") and await check_and_increment_ai_usage(current_user):
        try:
            fakten, nicht_gefunden = await _deck_fakten(req.deck_liste)
            prompt = (
                f"Roaste dieses Magic the Gathering Deck auf Deutsch unter Berücksichtigung des Formats: '{req.format}'.\n"
                f"Sei extrem sarkastisch, humorvoll, gemein aber augenzwinkernd. Nutze typischen Magic-Slang (z.B. Salz, Jank, Mana-Flooded, Netdecker, Comboplayer, Casual, etc.).\n"
                f"Kritisiere Kartenwahlen, eventuelle Instabilitäten, Klischees des Commanders oder Formats.\n\n"
                f"Gib die Antwort EXAKT als JSON (ohne Markdown Code Block) mit den folgenden Schlüsseln zurück:\n"
                f"- 'roast' (string, ausführlicher humorvoller Text, mind. 120 Wörter)\n"
                f"- 'salt_score' (int, Wert von 1-100 wie 'salzig' / nervig das Deck ist)\n"
                f"- 'verdict' (string, eine kurze, witzige Zusammenfassung / Urteil, z.B. 'Der wandelnde Salzstreuer')\n\n"
                + _fakten_abschnitt(fakten, nicht_gefunden)
                + f"Deckliste:\n{req.deck_liste}"
            )
            response = await asyncio.to_thread(
                modell_fuer("deck_roast").generate_content, prompt, None,
                "deck_roast", current_user
            )
            text_resp = response.text
            match = re.search(r'\{.*\}', text_resp, re.DOTALL)
            if match:
                text_resp = match.group(0)

            result = json.loads(text_resp)
            scryfall_cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.exception("Error generating deck roast")
            await gutschreiben(current_user)
            
    fallback_res = {
        # Auch hier keine erfundene Bewertung: salt_score 50 sah aus wie ein
        # Ergebnis, war aber nur ein Platzhalter.
        "nicht_verfuegbar": True,
        "roast": "Der Roast ist momentan nicht verfügbar. Bitte versuche es später erneut.",
        "salt_score": None,
        "verdict": None
    }
    return fallback_res

# ======================================================================
# POST /api/deck/validate – Validierung nach Formatregeln
# ======================================================================
@router.post(
    "/deck/validate",
    summary="Deck-Validierung",
)
@limiter.limit("120/minute")
async def validate_deck(req: ValidateDeckReq, request: Request, current_user: str = Depends(get_current_user)):
    try:
        result = await FormatValidator.validate_deck(req.deck_liste, req.format, fetch_card_details_cached)
        return result
    except Exception as e:
        logger.exception("Error in validate_deck")
        return {
            "legal": False,
            "errors": [f"Fehler bei der Deck-Validierung: {str(e)}"],
            "warnings": [],
            "details": {"format": req.format, "total_cards": 0}
        }

# ======================================================================
# Gemeinsame Helfer für die drei Bearbeitungs-Endpunkte
# ----------------------------------------------------------------------
# Laden, Besitz prüfen, speichern -- dreimal derselbe Ablauf. Stand er dreimal
# ausgeschrieben da, reichte ein vergessener Besitzcheck, damit ein fremdes Deck
# bearbeitbar wird.
# ======================================================================
class _DeckFehler(Exception):
    """Ein Grund, den der Nutzer lesen darf (nicht gefunden, kein Zugriff)."""


@asynccontextmanager
async def _deck_zum_bearbeiten(deck_id: int, benutzer: str):
    """Öffnet ein Deck des angemeldeten Nutzers zum Bearbeiten.

    Liefert (session, liste). Wirft _DeckFehler, wenn es das Deck nicht gibt
    oder es jemand anderem gehört.
    """
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT liste, benutzername FROM decks WHERE id = :id"),
            {"id": deck_id},
        )
        row = res.mappings().first()
        if not row:
            raise _DeckFehler("Deck nicht gefunden.")
        if row["benutzername"] != benutzer:
            raise _DeckFehler("Kein Zugriff auf dieses Deck.")
        yield session, (row["liste"] or "")


async def _deck_speichern(session, deck_id: int, liste: str) -> None:
    await session.execute(
        text("UPDATE decks SET liste = :list, aktualisiert_am = CURRENT_TIMESTAMP WHERE id = :id"),
        {"list": liste, "id": deck_id},
    )


# ======================================================================
# POST /api/deck/add-card – Karte dem Deck hinzufügen
# ======================================================================
@router.post(
    "/deck/add-card",
    summary="Karte zu Deck hinzufügen",
)
async def add_card_to_deck(req: DeckAddCardReq, current_user: str = Depends(get_current_user)):
    """Ein Exemplar mehr im Deck.

    'set'/'sammlernummer' sind optional. Stehen sie dabei, meint der Nutzer
    genau diese Auflage -- sie bekommt eine eigene Zeile, statt dass eine andere
    Auflage derselben Karte stillschweigend hochgezählt wird.
    """
    try:
        async with _deck_zum_bearbeiten(req.deck_id, current_user) as (session, liste):
            neue_liste = karte_hinzufuegen(liste, req.card_name, req.set, req.sammlernummer)
            await _deck_speichern(session, req.deck_id, neue_liste)
        return {"erfolg": True, "deck_liste": neue_liste}
    except _DeckFehler as e:
        return {"erfolg": False, "error": str(e)}
    except Exception:
        # Kein str(e) an den Client: die Meldung kann Dateipfade oder
        # SQL-Fragmente enthalten. Die Einzelheiten stehen im Log.
        logger.exception("Fehler beim Hinzufügen der Karte zum Deck")
        return {"erfolg": False, "error": "Die Karte konnte nicht hinzugefügt werden."}


# ======================================================================
# POST /api/deck/auflage – Auflage einer Karte im Deck wechseln
# ======================================================================
@router.post(
    "/deck/auflage",
    summary="Auflage einer Karte im Deck festlegen",
)
@limiter.limit("120/minute")
async def deck_auflage_setzen(req: DeckAuflageReq, request: Request,
                              current_user: str = Depends(get_current_user)):
    """Legt fest, WELCHE Version einer Karte im Deck steckt.

    Die Auflage steuert Bild und Preis. Für den Abgleich mit der Sammlung zählt
    weiterhin jede Auflage: Wer einen Bolt aus 2XM besitzt, dem fehlt keiner,
    bloss weil im Deck der aus M10 steht.
    """
    try:
        async with _deck_zum_bearbeiten(req.deck_id, current_user) as (session, liste):
            neue_liste, gefunden = auflage_setzen(
                liste, req.card_name, req.alt_set, req.alt_sammlernummer,
                req.set, req.sammlernummer)
            if not gefunden:
                return {"erfolg": False,
                        "error": f"'{req.card_name}' steht nicht in diesem Deck."}
            await _deck_speichern(session, req.deck_id, neue_liste)
        return {"erfolg": True, "deck_liste": neue_liste}
    except _DeckFehler as e:
        return {"erfolg": False, "error": str(e)}
    except Exception:
        logger.exception("Fehler beim Wechsel der Auflage")
        return {"erfolg": False, "error": "Die Auflage konnte nicht geändert werden."}

# ======================================================================
# POST /api/deck/remove-card – Karte aus Deck entfernen
# ======================================================================
@router.post(
    "/deck/remove-card",
    summary="Karte aus Deck entfernen",
)
async def remove_card_from_deck(req: DeckRemoveCardReq, current_user: str = Depends(get_current_user)):
    """Ein Exemplar weniger. Mit 'set'/'sammlernummer' aus genau dieser Auflage."""
    try:
        async with _deck_zum_bearbeiten(req.deck_id, current_user) as (session, liste):
            neue_liste, gefunden = karte_entfernen(
                liste, req.card_name, req.set, req.sammlernummer)
            if not gefunden:
                return {"erfolg": False,
                        "error": f"Karte '{req.card_name}' nicht im Deck gefunden."}
            await _deck_speichern(session, req.deck_id, neue_liste)
        return {"erfolg": True, "deck_liste": neue_liste}
    except _DeckFehler as e:
        return {"erfolg": False, "error": str(e)}
    except Exception:
        logger.exception("Fehler beim Entfernen der Karte aus dem Deck")
        return {"erfolg": False, "error": "Die Karte konnte nicht entfernt werden."}


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
        logger.exception("Fehler beim Laden des geteilten Decks")
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

            # 2. Anzahl Karten in allen Sammlungen.
            #
            # Vorher: SUM(anzahl) -- die Spalte `anzahl` wird von den Roh-SQL-
            # Inserts aber nie gesetzt und ist damit immer NULL, sodass hier
            # dauerhaft 0 stand, egal wie viele Karten gespeichert waren.
            # Jede Zeile entspricht genau einer physischen Karte (mehrere
            # Exemplare = mehrere Zeilen), also ist COUNT die richtige Zahl.
            # Platzhalter-Zeilen leerer Alben zählen nicht mit.
            res_collection = await session.execute(
                text("SELECT COUNT(*) FROM sammlung_alben WHERE karten_name != '__PLACEHOLDER__'")
            )
            collection_count = res_collection.scalar() or 0

            # 3. Echte Anzahl angelegter Alben (über alle Nutzer). Der frühere
            # "query_count" war eine erfundene Formel (decks*12+karten*3+1420)
            # -- keine Fake-Metriken im Dashboard.
            res_albums = await session.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "SELECT DISTINCT benutzername, album_name FROM sammlung_alben"
                    ") AS alben"
                )
            )
            albums_count = res_albums.scalar() or 0

            return {
                "total_decks": decks_count,
                "total_collection_cards": collection_count,
                "total_albums": albums_count,
            }
    except Exception as e:
        logger.exception("Fehler beim Laden der Dashboard-Statistiken")
        return {
            "total_decks": 0,
            "total_collection_cards": 0,
            "total_albums": 0,
        }


