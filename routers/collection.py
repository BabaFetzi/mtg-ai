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
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db_session, check_user_premium
from services.scryfall import fetch_card_details_cached

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
async def get_sammlung(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
            {"name": benutzername}
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
async def add_karte(data: AddKarteData):
    async with get_db_session() as session:
        await session.execute(
            text("INSERT INTO sammlung_alben (benutzername, karten_name, album_name, bild_url, preis) "
                 "VALUES (:user, :name, :album, :url, :price)"),
            {"user": data.benutzername, "name": data.karten_name, "album": data.album_name, "url": data.bild_url, "price": data.preis}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/sammlung/loeschen – Karte entfernen
# ======================================================================
@router.post(
    "/sammlung/loeschen",
    summary="Karte aus Sammlung löschen",
)
async def delete_karte(data: DeleteKarteData):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE id = :id"),
            {"id": data.karten_id}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/sammlung/album_loeschen – Album löschen
# ======================================================================
@router.post(
    "/sammlung/album_loeschen",
    summary="Gesamtes Album löschen",
)
async def delete_album(data: DeleteAlbumData):
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM sammlung_alben WHERE benutzername = :user AND album_name = :album"),
            {"user": data.benutzername, "album": data.album_name}
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
    album: str = Query(default=None, description="Filter nach Albumname")
):
    try:
        async with get_db_session() as session:
            if album:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name = :album"),
                    {"name": benutzername, "album": album}
                )
            else:
                res = await session.execute(
                    text("SELECT * FROM sammlung_alben WHERE benutzername = :name AND album_name != 'Wunschliste'"),
                    {"name": benutzername}
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
        print(f"Fehler bei Sammlung-Filter: {e}")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# GET /api/sammlung/{benutzername}/editions – Alle Editionen listen
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/editions",
    summary="Editionen in der Sammlung abfragen",
)
async def sammlung_editions(benutzername: str, album: str = Query(default=None)):
    try:
        async with get_db_session() as session:
            if album:
                res = await session.execute(
                    text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name AND album_name = :album"),
                    {"name": benutzername, "album": album}
                )
            else:
                res = await session.execute(
                    text("SELECT DISTINCT karten_name FROM sammlung_alben WHERE benutzername = :name"),
                    {"name": benutzername}
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
        print(f"Fehler bei Editionen-Abfrage: {e}")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# Asynchroner Background-Task für CSV-Import
# ======================================================================
async def run_csv_import_task(job_id: str, csv_text: str, benutzername: str, album_name: str):
    try:
        reader = csv.reader(io.StringIO(csv_text))
        rows_to_insert = []
        imported = 0
        failed = 0
        errors_list = []
        
        # 1. Parse rows and collect card names
        rows_parsed = []
        unique_card_names = set()
        
        for row_num, row in enumerate(reader, start=1):
            if not row or (row_num == 1 and row[0].strip().lower() in ["kartenname", "name", "card"]):
                continue
                
            karten_name = row[0].strip() if len(row) > 0 else ""
            try:
                anzahl = int(row[1].strip()) if len(row) > 1 and row[1].strip() else 1
            except ValueError:
                anzahl = 1
            csv_edition = row[2].strip() if len(row) > 2 else ""
            csv_album = row[3].strip() if len(row) > 3 else album_name
            
            if not karten_name:
                failed += 1
                errors_list.append(f"Zeile {row_num}: Leerer Kartenname.")
                continue
                
            rows_parsed.append({
                "row_num": row_num,
                "name": karten_name,
                "anzahl": anzahl,
                "album": csv_album or album_name
            })
            unique_card_names.add(karten_name)
            
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
        print(f"Error in background CSV import: {e}")
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
    benutzername: str = Form(...),
    album_name: str = Form("Import")
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
            benutzername,
            album_name
        )
        
        return {"erfolg": True, "job_id": job_id}
    except Exception as e:
        print(f"Fehler beim Starten des CSV-Imports: {e}")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# GET /api/sammlung/import-status/{job_id} – Status abfragen
# ======================================================================
@router.get(
    "/sammlung/import-status/{job_id}",
    summary="Status eines CSV-Imports abfragen",
)
async def get_import_status(job_id: str):
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
async def sammlung_export_csv(benutzername: str):
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
                {"name": benutzername}
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
        print(f"Fehler beim CSV-Export: {e}")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})


# ======================================================================
# POST /api/sammlung/{benutzername}/refresh-prices – Preise aktualisieren
# ======================================================================
@router.post(
    "/sammlung/{benutzername}/refresh-prices",
    summary="Sammlungspreise live aktualisieren",
)
async def refresh_sammlung_prices(benutzername: str):
    is_premium = await check_user_premium(benutzername)
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
                {"name": benutzername}
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
        print(f"Fehler bei refresh_sammlung_prices: {e}")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})

