"""
routers/collection.py – Sammlungs- & Albenverwaltung (Galerie, Filter, In- & Export)

Endpoints:
    GET  /api/sammlung/{benutzername}          – Gesamte Sammlung eines Users abfragen
    POST /api/sammlung/hinzufuegen             – Einzelne Karte zur Sammlung hinzufügen
    POST /api/sammlung/loeschen                – Einzelne Karte aus der Sammlung löschen (nach ID)
    POST /api/sammlung/album_loeschen           – Gesamtes Album löschen
    GET  /api/sammlung/{benutzername}/filter   – Sammlung filtern (Farbe, Seltenheit, Edition, CMC, Typ, Text)
    GET  /api/sammlung/{benutzername}/editions  – Alle einzigartigen Editionen in der Sammlung listen
    POST /api/sammlung/import-csv              – CSV-Import von Karten in ein Album
    GET  /api/sammlung/{benutzername}/export-csv – CSV-Export der Sammlung

Abhängigkeiten:
    - database          → get_db_session()
    - services.scryfall  → fetch_card_details_cached()
    - schemas.models    → SammlungHinzufuegenReq, AlbumLoeschenReq
"""

import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session, check_user_premium
from services.scryfall import fetch_card_details_cached


# ======================================================================
# CSV-Import-Parsing (robust, testbar, ohne Netzwerk)
# ======================================================================
# Header-Aliase (deutsch + englisch), damit unterschiedliche Export-Tools
# (Moxfield, Deckbox, Archidekt, deutsches/englisches Excel) funktionieren.
_NAME_KEYS = {"kartenname", "name", "card", "card name", "cardname", "karte"}
_COUNT_KEYS = {"anzahl", "menge", "count", "quantity", "qty", "amount"}
_EDITION_KEYS = {"edition", "set", "set code", "set_code", "auflage"}
_ALBUM_KEYS = {"album", "ordner", "folder", "binder", "sammlung"}

# Führende Menge im Kartennamen: "1 Sol Ring", "2x Lightning Bolt", "3X Forest".
_LEADING_QTY = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.+)$")


def _split_leading_quantity(name_cell: str):
    """Trennt eine evtl. führende Menge vom Kartennamen ab.
    '2x Lightning Bolt' -> (2, 'Lightning Bolt'); 'Sol Ring' -> (None, 'Sol Ring')."""
    m = _LEADING_QTY.match(name_cell or "")
    if m:
        try:
            return int(m.group(1)), m.group(2).strip()
        except (ValueError, TypeError):
            pass
    return None, (name_cell or "").strip()


def _detect_delimiter(sample: str) -> str:
    """Erkennt das CSV-Trennzeichen (Komma/Semikolon/Tab). Deutsches Excel
    exportiert i.d.R. semikolon-getrennt -- ohne Erkennung schlug der Import
    dort komplett fehl."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        # Heuristik-Fallback: nimm das häufigste plausible Trennzeichen der 1. Zeile.
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first_line.count(d) for d in [",", ";", "\t"]}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def parse_import_csv(csv_text: str, default_album: str) -> List[Dict[str, Any]]:
    """
    Parst eine Import-CSV robust in eine Liste von {name, anzahl, edition, album}.

    Behebt die Ursachen des Import-Bugs (falsche/gleiche Karte in Alben):
    - erkennt Komma-, Semikolon- und Tab-Trennung (deutsches Excel = Semikolon),
    - ordnet Spalten anhand der Header-Namen zu (statt fester Positionen), mit
      positionsbasiertem Fallback [Name, Anzahl, Edition, Album],
    - entfernt eine führende Menge aus dem Kartennamen ('1 Sol Ring').

    Reine Funktion (kein Netzwerk) -> unittestbar.
    """
    if not csv_text or not csv_text.strip():
        return []

    delimiter = _detect_delimiter(csv_text[:4096])
    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        return []

    # Spalten-Mapping über Header bestimmen, sonst Standard-Positionen.
    header = [(c or "").strip().lower() for c in rows[0]]
    has_header = any(h in _NAME_KEYS for h in header)
    col = {"name": 0, "count": 1, "edition": 2, "album": 3}
    if has_header:
        col = {"name": None, "count": None, "edition": None, "album": None}
        for idx, h in enumerate(header):
            if col["name"] is None and h in _NAME_KEYS:
                col["name"] = idx
            elif col["count"] is None and h in _COUNT_KEYS:
                col["count"] = idx
            elif col["edition"] is None and h in _EDITION_KEYS:
                col["edition"] = idx
            elif col["album"] is None and h in _ALBUM_KEYS:
                col["album"] = idx
        if col["name"] is None:
            col["name"] = 0
        data_rows = rows[1:]
    else:
        data_rows = rows

    def _cell(row, key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    parsed = []
    for row in data_rows:
        raw_name = _cell(row, "name")
        if not raw_name:
            continue

        leading_qty, name = _split_leading_quantity(raw_name)
        if not name:
            continue

        count_cell = _cell(row, "count")
        anzahl = None
        if count_cell:
            try:
                anzahl = int(float(count_cell.replace(",", ".")))
            except (ValueError, TypeError):
                anzahl = None
        if anzahl is None:
            anzahl = leading_qty if leading_qty is not None else 1
        if anzahl < 1:
            anzahl = 1

        album = _cell(row, "album") or default_album
        parsed.append({
            "name": name,
            "anzahl": anzahl,
            "edition": _cell(row, "edition"),
            "album": album,
        })
    return parsed

logger = logging.getLogger(__name__)

# ======================================================================
# Lokale Request Models (zur Kompatibilität mit originalen Signaturen)
# ======================================================================
class DeleteKarteData(BaseModel):
    karten_id: int

class DeleteAlbumData(BaseModel):
    benutzername: str
    album_name: str

class AddKarteData(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str
    bild_url: str = ""
    preis: str = "0.00"

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["Sammlung"],
)

# ======================================================================
# GET /api/sammlung/{benutzername} – Gesamte Sammlung abrufen
# ======================================================================
@router.get(
    "/sammlung/{benutzername}",
    summary="Sammlung abrufen",
)
async def get_sammlung(benutzername: str, current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
            {"name": current_user}
        )
        rows = res.mappings().all()
        
        unique_names = list(set(row["karten_name"] for row in rows if row["karten_name"] != "__PLACEHOLDER__"))
        scryfall_data = await fetch_card_details_cached(unique_names)
        
        alben = {}
        for row in rows:
            album = row["album_name"]
            if album not in alben:
                alben[album] = []
            
            karten_name = row["karten_name"]
            card_info = scryfall_data.get(karten_name.lower().strip())
            
            live_preis = card_info.get("price", row["preis"]) if card_info else row["preis"]
            live_bild = card_info.get("image", row["bild_url"]) if card_info else row["bild_url"]
            
            alben[album].append({
                "id": row["id"],
                "name": karten_name,
                "bild_url": live_bild,
                "preis": row["preis"],
                "livePreis": live_preis
            })
        return {"erfolg": True, "alben": alben}

# ======================================================================
# POST /api/sammlung/hinzufuegen – Karte hinzufügen
# ======================================================================
@router.post(
    "/sammlung/hinzufuegen",
    summary="Karte zur Sammlung hinzufügen",
)
async def add_karte(data: AddKarteData, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
                 "VALUES (:user, :name, :album, :url, :price)"),
            {"user": current_user, "name": data.karten_name, "album": data.album_name, "url": data.bild_url, "price": data.preis}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/sammlung/loeschen – Karte entfernen
# ======================================================================
@router.post(
    "/sammlung/loeschen",
    summary="Karte aus Sammlung löschen",
)
async def delete_karte(data: DeleteKarteData, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE id = :id AND benutzername = :user"),
            {"id": data.karten_id, "user": current_user}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/sammlung/album_loeschen – Album löschen
# ======================================================================
@router.post(
    "/sammlung/album_loeschen",
    summary="Gesamtes Album löschen",
)
async def delete_album(data: DeleteAlbumData, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE benutzername = :user AND album_name = :album"),
            {"user": current_user, "album": data.album_name}
        )
    return {"erfolg": True}

# ======================================================================
# GET /api/sammlung/{benutzername}/filter – Filterung der Sammlung
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/filter",
    summary="Sammlung filtern",
)
async def sammlung_filter(
    benutzername: str,
    farbe: str = Query(default=None, description="Farbe (W, U, B, R, G)"),
    seltenheit: str = Query(default=None, description="Seltenheit (common, uncommon, rare, mythic)"),
    edition: str = Query(default=None, description="Edition / Set-Code"),
    manakosten_min: int = Query(default=None, description="Minimale Manakosten (CMC)"),
    manakosten_max: int = Query(default=None, description="Maximale Manakosten (CMC)"),
    typ: str = Query(default=None, description="Kartentyp (Creature, Instant, Sorcery, ...)"),
    suche: str = Query(default=None, description="Freitextsuche im Kartennamen"),
    album: str = Query(default=None, description="Filter nach Albumname"),
    current_user: str = Depends(get_current_user),
):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    try:
        async with get_db_session() as session:
            if album:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name = :album"),
                    {"name": current_user, "album": album}
                )
            else:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name != 'Wunschliste'"),
                    {"name": current_user}
                )
            rows = res.mappings().all()

        if not rows:
            return {"erfolg": True, "karten": []}

        unique_names = list(set(row["karten_name"] for row in rows))
        scryfall_data = await fetch_card_details_cached(unique_names)

        result = []
        for row in rows:
            name_lower = row["karten_name"].lower().strip()
            card_info = scryfall_data.get(name_lower)
            if not card_info:
                continue

            # Freitextsuche im Namen
            if suche and suche.lower() not in card_info.get("name", "").lower():
                continue

            # Farbfilter
            if farbe:
                card_colors = card_info.get("colors", []) or card_info.get("color_identity", [])
                if farbe.upper() not in [c.upper() for c in card_colors]:
                    continue

            # Seltenheit
            if seltenheit:
                card_rarity = card_info.get("rarity", "").lower()
                if card_rarity != seltenheit.lower():
                    continue

            # Edition / Set
            if edition:
                card_set = card_info.get("set", "").lower()
                if card_set != edition.lower():
                    continue

            # Manakosten min/max
            try:
                card_cmc = float(card_info.get("cmc", 0))
            except (ValueError, TypeError):
                card_cmc = 0.0
            if manakosten_min is not None and card_cmc < manakosten_min:
                continue
            if manakosten_max is not None and card_cmc > manakosten_max:
                continue

            # Typfilter
            if typ:
                card_type = card_info.get("type", "").lower()
                if typ.lower() not in card_type:
                    continue

            result.append({
                "id": row["id"],
                "name": card_info.get("name", row["karten_name"]),
                "type": card_info.get("type", ""),
                "colors": card_info.get("colors", []),
                "cmc": card_info.get("cmc", 0),
                "rarity": card_info.get("rarity", ""),
                "set": card_info.get("set", ""),
                "image_url": card_info.get("image", row["bild_url"]),
                "price": card_info.get("price", row["preis"]),
                "originalPrice": row["preis"],
                "album_name": row["album_name"]
            })

        return {"erfolg": True, "karten": result}
    except Exception as e:
        logger.exception("Fehler bei Sammlung-Filter")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# GET /api/sammlung/{benutzername}/editions – Alle Editionen listen
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/editions",
    summary="Editionen in der Sammlung abfragen",
)
async def sammlung_editions(benutzername: str, album: str = Query(default=None), current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    try:
        async with get_db_session() as session:
            if album:
                res = await session.execute(
                    text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name AND album_name = :album"),
                    {"name": current_user, "album": album}
                )
            else:
                res = await session.execute(
                    text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name"),
                    {"name": current_user}
                )
            rows = res.mappings().all()

        if not rows:
            return {"erfolg": True, "editions": []}

        unique_names = [row["karten_name"] for row in rows]
        scryfall_data = await fetch_card_details_cached(unique_names)

        editions_seen = set()
        editions = []
        for card_info in scryfall_data.values():
            set_code = card_info.get("set", "")
            set_name = card_info.get("set_name", set_code)
            if set_code and set_code not in editions_seen:
                editions_seen.add(set_code)
                editions.append({"set_code": set_code, "set_name": set_name})

        editions.sort(key=lambda e: e["set_name"])
        return {"erfolg": True, "editions": editions}
    except Exception as e:
        logger.exception("Fehler bei Editionen-Abfrage")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# Asynchroner Background-Task für CSV-Import
# ======================================================================
async def run_csv_import_task(job_id: str, csv_text: str, benutzername: str, album_name: str):
    try:
        rows_to_insert = []
        imported = 0
        failed = 0
        errors_list = []
        
        # 1. Robust parsen (Delimiter-Erkennung, Header-Spalten-Mapping, Mengen-Strip)
        parsed_entries = parse_import_csv(csv_text, album_name)
        rows_parsed = []
        unique_card_names = set()
        for i, entry in enumerate(parsed_entries, start=1):
            rows_parsed.append({
                "row_num": i,
                "name": entry["name"],
                "anzahl": entry["anzahl"],
                "album": entry["album"],
            })
            unique_card_names.add(entry["name"])

        # 2. Batch-fetch Scryfall data
        scryfall_data = await fetch_card_details_cached(list(unique_card_names))
        
        # 3. Match and build insert list
        for r in rows_parsed:
            name_lower = r["name"].lower().strip()
            card_info = scryfall_data.get(name_lower)
            
            if not card_info:
                failed += r["anzahl"]
                errors_list.append(f"Zeile {r['row_num']}: Karte '{r['name']}' nicht in Scryfall gefunden.")
                continue
                
            canonical_name = card_info.get("name", r["name"])
            bild_url = card_info.get("image", "")
            price_val = card_info.get("price", "0.00")
            
            for _ in range(r["anzahl"]):
                rows_to_insert.append({
                    "user": benutzername,
                    "name": canonical_name,
                    "album": r["album"],
                    "url": bild_url,
                    "price": str(price_val)
                })
            imported += r["anzahl"]
            
        # 4. Insert into database
        if rows_to_insert:
            async with get_db_session() as session:
                await session.execute(
                    text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
                         "VALUES (:user, :name, :album, :url, :price)"),
                    [{"user": r["user"], "name": r["name"], "album": r["album"], "url": r["url"], "price": r["price"]} for r in rows_to_insert]
                )
                
        # 5. Update job status to completed
        result_json = json.dumps({
            "imported": imported,
            "failed": failed,
            "errors": errors_list
        })
        async with get_db_session() as session:
            await session.execute(
                text("UPDATE import_jobs SET status = 'completed', result = :res WHERE job_id = :id"),
                {"res": result_json, "id": job_id}
            )
            
    except Exception as e:
        logger.exception("Error in background CSV import")
        async with get_db_session() as session:
            await session.execute(
                text("UPDATE import_jobs SET status = 'failed', error = :err WHERE job_id = :id"),
                {"err": str(e), "id": job_id}
            )

# ======================================================================
# POST /api/sammlung/import-csv – CSV-Import (Background-Task)
# ======================================================================
@router.post(
    "/sammlung/import-csv",
    summary="CSV-Kartenliste importieren",
)
async def sammlung_import_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    album_name: str = Form("Import"),
    current_user: str = Depends(get_current_user),
):
    try:
        content = await file.read()
        csv_text = content.decode("utf-8-sig")

        job_id = str(uuid.uuid4())

        # Save job record
        async with get_db_session() as session:
            await session.execute(
                text("INSERT INTO import_jobs (job_id, status, erstellt_am) VALUES (:id, 'processing', :now)"),
                {"id": job_id, "now": datetime.utcnow()}
            )

        background_tasks.add_task(
            run_csv_import_task,
            job_id,
            csv_text,
            current_user,
            album_name
        )
        
        return {"erfolg": True, "job_id": job_id}
    except Exception as e:
        logger.exception("Fehler beim Starten des CSV-Imports")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# GET /api/sammlung/import-status/{job_id} – Status abfragen
# ======================================================================
@router.get(
    "/sammlung/import-status/{job_id}",
    summary="Status eines CSV-Imports abfragen",
)
async def get_import_status(job_id: str, current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM import_jobs WHERE job_id = :id"),
            {"id": job_id}
        )
        row = res.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Job nicht gefunden")
            
        result_data = None
        if row["result"]:
            result_data = json.loads(row["result"])
            
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "error": row["error"],
            "result": result_data
        }

# ======================================================================
# GET /api/sammlung/{benutzername}/export-csv – CSV-Export
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/export-csv",
    summary="Sammlung als CSV exportieren",
)
async def sammlung_export_csv(benutzername: str, current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
                {"name": current_user}
            )
            rows = res.mappings().all()

        aggregated = {}
        for row in rows:
            key = (row["karten_name"], row["album_name"])
            if key not in aggregated:
                aggregated[key] = {"anzahl": 0, "preis": row["preis"]}
            aggregated[key]["anzahl"] += 1

        unique_names = list(set(k[0] for k in aggregated.keys()))
        scryfall_data = await fetch_card_details_cached(unique_names) if unique_names else {}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Kartenname", "Anzahl", "Edition", "Album", "Preis_EUR"])

        for (karten_name, album_name), info in sorted(aggregated.items()):
            name_lower = karten_name.lower().strip()
            card_info = scryfall_data.get(name_lower, {})
            edition_code = card_info.get("set", "")
            price_eur = card_info.get("price", info["preis"]) or info["preis"]
            writer.writerow([
                card_info.get("name", karten_name),
                info["anzahl"],
                edition_code,
                album_name,
                price_eur
            ])

        csv_content = output.getvalue()
        output.close()

        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8-sig")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="sammlung_{benutzername}.csv"'
            }
        )
    except Exception as e:
        logger.exception("Fehler beim CSV-Export")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})


# ======================================================================
# POST /api/sammlung/{benutzername}/refresh-prices – Preise aktualisieren
# ======================================================================
@router.post(
    "/sammlung/{benutzername}/refresh-prices",
    summary="Sammlungspreise live aktualisieren",
)
async def refresh_sammlung_prices(benutzername: str, current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    is_premium = await check_user_premium(current_user)
    if not is_premium:
        return JSONResponse(
            status_code=403,
            content={"erfolg": False, "error": "Paywall: Dieses Feature steht nur Premium-Mitgliedern zur Verfügung."}
        )
    try:
        # 1. Alle einzigartigen Karten des Benutzers aus der DB holen
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name AND karten_name != '__PLACEHOLDER__'"),
                {"name": current_user}
            )
            rows = res.mappings().all()
            
        unique_names = [row["karten_name"] for row in rows]
        if not unique_names:
            return {"erfolg": True, "nachricht": "Keine Karten in der Sammlung vorhanden."}
            
        # 2. Aus dem Cache löschen
        from services.cache import scryfall_cache
        for name in unique_names:
            clean_name = name.lower().strip()
            scryfall_cache.delete(f"card:{clean_name}")
            if "//" in clean_name:
                front_face = clean_name.split("//")[0].strip()
                scryfall_cache.delete(f"card:{front_face}")
                
        # 3. Frisch von Scryfall holen (schreibt es direkt neu in den Cache)
        await fetch_card_details_cached(unique_names)
        
        return {"erfolg": True}
    except Exception as e:
        logger.exception("Fehler bei refresh_sammlung_prices")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})

