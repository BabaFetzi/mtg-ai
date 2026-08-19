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

import asyncio
import csv
import io
import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from fastapi import (APIRouter, UploadFile, File, Form, Query, HTTPException,
                     BackgroundTasks, Depends, Request)
from fastapi.responses import StreamingResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session, check_user_premium
from services.antwort import json_antwort
from services.limiter import limiter
from services.bestand import bedarf_aus_deck, bestand_aus_zeilen, fehlende_exemplare
from services.scryfall import (DRUCK_CACHE_PRAEFIX, druck_nach_id, druecke_nach_ids,
                               drucke_fuer_deck, fetch_card_details_cached, parse_decklist,
                               preis_fuer_variante)


# ======================================================================
# CSV-Import-Parsing (robust, testbar, ohne Netzwerk)
# ======================================================================
# Header-Aliase (deutsch + englisch), damit unterschiedliche Export-Tools
# (Moxfield, Deckbox, Archidekt, deutsches/englisches Excel) funktionieren.
_NAME_KEYS = {"kartenname", "name", "card", "card name", "cardname", "karte"}
_COUNT_KEYS = {"anzahl", "menge", "count", "quantity", "qty", "amount"}
_EDITION_KEYS = {"edition", "set", "set code", "set_code", "auflage"}
_ALBUM_KEYS = {"album", "ordner", "folder", "binder", "sammlung"}
_SPRACHE_KEYS = {"sprache", "language", "lang", "sprache_karte"}
_FOIL_KEYS = {"foil", "veredelt", "premium"}

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
    col = {"name": 0, "count": 1, "edition": 2, "album": 3, "sprache": None, "foil": None}
    if has_header:
        col = {"name": None, "count": None, "edition": None, "album": None,
               "sprache": None, "foil": None}
        for idx, h in enumerate(header):
            if col["name"] is None and h in _NAME_KEYS:
                col["name"] = idx
            elif col["count"] is None and h in _COUNT_KEYS:
                col["count"] = idx
            elif col["edition"] is None and h in _EDITION_KEYS:
                col["edition"] = idx
            elif col["album"] is None and h in _ALBUM_KEYS:
                col["album"] = idx
            elif col["sprache"] is None and h in _SPRACHE_KEYS:
                col["sprache"] = idx
            elif col["foil"] is None and h in _FOIL_KEYS:
                col["foil"] = idx
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
        # Sprache und Foil nur übernehmen, wenn die Datei sie nennt. Fehlt die
        # Spalte, bleibt die Angabe leer statt geraten -- ein eigener Export
        # der App liest sich damit wieder vollständig ein.
        foil_zelle = _cell(row, "foil").lower()
        parsed.append({
            "name": name,
            "anzahl": anzahl,
            "edition": _cell(row, "edition"),
            "album": album,
            "sprache": _cell(row, "sprache").lower(),
            "foil": foil_zelle in {"ja", "yes", "true", "1", "x", "foil"},
        })
    return parsed

logger = logging.getLogger(__name__)

# ======================================================================
# Drosselung
# ======================================================================
# Diese Datei hatte KEINE einzige Grenze, während routers/decks.py sechs hat.
# Das fiel nicht auf, weil slowapi ohne default_limits nur dort greift, wo ein
# Dekorator steht -- ein fehlender Dekorator sieht aus wie kein Problem.
#
# Gezählt wird je angemeldetem Nutzer (services/limiter.py), nicht je IP.
# Die Zahlen richten sich danach, was eine Anfrage kostet:
#
#   240/min  Schreiben einzelner Karten, Ordnernamen -- klein und häufig.
#            Wer eine Sammlung einpflegt, klickt schnell.
#   120/min  Ordnerübersicht, Filter, Editionen. Eine Filterseite je Klick,
#            dazu "Mehr laden" -- 120 lässt zügiges Blättern zu.
#    60/min  Top-Liste und Kartennamen: seltener gebraucht, aber sie lesen
#            die gesamte Sammlung.
#    30/min  Ordner löschen, Deckübernahme -- selten und weitreichend.
#    10/min  Vollabruf, CSV-Import und -Export. Jeder Aufruf liest die
#            komplette Sammlung; die Oberfläche braucht das höchstens einmal.
#     5/min  Preisaktualisierung: fragt Scryfall für jede Karte an. Ohne
#            Grenze könnte ein einzelner Nutzer damit sowohl den Server als
#            auch das Kontingent bei Scryfall aufbrauchen.

# ======================================================================
# Strukturierte Kartenmetadaten
# ======================================================================
# Die Spalten scryfall_id/edition/seltenheit/farben/manakosten/kartentyp waren
# im Schema vorhanden, wurden aber von KEINEM Insert befüllt -- deshalb musste
# der Sammlungsfilter alle Zeilen laden, über das Netz auflösen und in Python
# filtern. Beim Speichern liegen die Daten ohnehin vor; sie werden jetzt
# mitgeschrieben und machen die Sammlung echt abfragbar.
_SAMMLUNG_INSERT_SQL = (
    "INSERT INTO sammlung_alben "
    "(benutzername, karten_name, album_name, bild_url, preis, "
    " edition, seltenheit, farben, manakosten, kartentyp, foil, sprache, "
    " scryfall_id, sammlernummer, zustand) "
    "VALUES (:user, :name, :album, :url, :price, "
    " :edition, :seltenheit, :farben, :manakosten, :kartentyp, :foil, :sprache, "
    " :scryfall_id, :sammlernummer, :zustand)"
)


def ist_foil(row) -> bool:
    """NULL wie False lesen -- Zeilen aus der Zeit vor der Foil-Spalte haben
    keinen Wert und sind normale Karten."""
    try:
        return bool(row["foil"])
    except (KeyError, IndexError, TypeError):
        return False


SPRACHEN = {
    "en": "Englisch", "de": "Deutsch", "fr": "Französisch", "it": "Italienisch",
    "es": "Spanisch", "pt": "Portugiesisch", "ja": "Japanisch", "ko": "Koreanisch",
    "ru": "Russisch", "zhs": "Chinesisch (vereinfacht)", "zht": "Chinesisch (traditionell)",
    "ph": "Phyrexianisch",
}


# Die übliche Zustandsskala im Kartenhandel (Cardmarket).
ZUSTAENDE = {
    "M": "Mint",
    "NM": "Near Mint",
    "EX": "Excellent",
    "GD": "Good",
    "LP": "Light Played",
    "PL": "Played",
    "PO": "Poor",
}


def zustand_von(row) -> Optional[str]:
    """Zustand der Zeile oder None.

    Alte Zeilen haben keinen -- sie als "Near Mint" auszugeben wäre eine
    erfundene Angabe über fremdes Eigentum.
    """
    try:
        wert = row["zustand"]
    except (KeyError, IndexError, TypeError):
        return None
    wert = (wert or "").strip().upper()
    return wert if wert in ZUSTAENDE else None


def druck_von(row) -> Dict[str, Any]:
    """Angaben zum besessenen Druck (Auflage, Sammlernummer, Kennung)."""
    def feld(name):
        try:
            wert = row[name]
        except (KeyError, IndexError, TypeError):
            return None
        wert = (wert or "").strip() if isinstance(wert, str) else wert
        return wert or None

    return {
        "edition": feld("edition"),
        "sammlernummer": feld("sammlernummer"),
        "scryfall_id": feld("scryfall_id"),
    }


def sprache_von(row) -> Optional[str]:
    """Sprache der Zeile oder None.

    NULL heisst "nicht erfasst" -- Zeilen aus der Zeit vor dieser Spalte
    einfach als Englisch auszugeben, wäre eine erfundene Angabe.
    """
    try:
        wert = row["sprache"]
    except (KeyError, IndexError, TypeError):
        return None
    wert = (wert or "").strip().lower()
    return wert or None


def live_preis_fuer(card_info: Optional[Dict[str, Any]], row, ersatz) -> str:
    """Aktueller Marktpreis passend zur Ausführung dieser Zeile.

    Vorher wurde immer card_info["price"] genommen -- also der Normalpreis,
    auch für eine Foil-Karte. Damit war der Sammlungswert einer Foil-Sammlung
    systematisch zu niedrig, und über den früheren Fall-through konnte umgekehrt
    eine normale Karte den Foil-Preis bekommen.
    """
    if not card_info:
        return ersatz
    passend = preis_fuer_variante(card_info.get("prices") or {}, foil=ist_foil(row))
    if passend:
        return passend
    # Keine Angabe für diese Ausführung: lieber der zuletzt gespeicherte Wert
    # als ein Preis der jeweils anderen Ausführung.
    return ersatz


async def kartendaten_fuer_zeilen(rows) -> Dict[Any, Dict[str, Any]]:
    """Kartendaten je Sammlungszeile -- vorrangig aus dem gespeicherten Druck.

    Ohne das wurde für jede Zeile der Standarddruck angesetzt. Wer einen alten
    Druck besitzt, sah den Preis des neuesten Nachdrucks; bei alten Karten ist
    das ein Vielfaches. Zeilen ohne gespeicherten Druck (Altbestand, CSV-Import)
    fallen weiterhin auf den Namen zurück -- eine Zeile ohne Preis wäre
    schlechter als eine mit ungefährem.
    """
    # Die Kennung einmal je Zeile bestimmen. druck_von() baut ein neues dict
    # und lief vorher dreimal pro Zeile -- bei 15000 Karten ist das messbar.
    kennungen = [(r, druck_von(r)["scryfall_id"] or "") for r in rows]

    ids = [k for _, k in kennungen if k]
    namen = [r["karten_name"] for r, k in kennungen if not k]

    nach_id: Dict[str, Dict[str, Any]] = {}
    if ids:
        try:
            nach_id = await druecke_nach_ids(ids)
        except Exception:
            logger.warning("Drucke nicht auflösbar -- weiche auf die Namen aus", exc_info=True)

    # Namen aller Zeilen holen, für die es keinen (auflösbaren) Druck gibt.
    fehlend = [r["karten_name"] for r, k in kennungen if not nach_id.get(k)]
    nach_name: Dict[str, Dict[str, Any]] = {}
    if namen or fehlend:
        nach_name = await fetch_card_details_cached(list({*namen, *fehlend}))

    zuordnung: Dict[Any, Dict[str, Any]] = {}
    for r, kennung in kennungen:
        info = nach_id.get(kennung) or nach_name.get((r["karten_name"] or "").lower().strip())
        if info:
            zuordnung[r["id"]] = info
    return zuordnung


def karten_metadaten(card_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Wandelt ein Scryfall-card_info in die strukturierten Spaltenwerte.

    Fehlt card_info (Scryfall nicht erreichbar), werden NULL-Werte geliefert --
    die Zeile wird trotzdem gespeichert und kann später nachgefüllt werden.
    """
    if not card_info:
        return {"edition": None, "seltenheit": None, "farben": None,
                "manakosten": None, "kartentyp": None}

    try:
        manakosten = int(float(card_info.get("cmc") or 0))
    except (TypeError, ValueError):
        manakosten = None

    farben = card_info.get("colors") or card_info.get("color_identity") or []
    return {
        "edition": (card_info.get("set") or None),
        "seltenheit": (card_info.get("rarity") or None),
        # 'W,U' -- Suche erfolgt per LIKE '%W%'
        "farben": (",".join(farben) if farben else ""),
        "manakosten": manakosten,
        "kartentyp": (card_info.get("type") or None),
    }

async def backfill_kartenmetadaten(limit: int = 200) -> int:
    """Füllt die strukturierten Spalten für Alt-Zeilen nach.

    Zeilen, die vor dieser Änderung gespeichert wurden, haben leere Metadaten.
    Der Filter arbeitet für sie weiterhin korrekt (NULL-Zeilen werden in Python
    geprüft), aber ohne Nachfüllen bliebe die Sammlung dauerhaft halb
    strukturiert. Die Wartungsaufgabe ruft das in kleinen Portionen auf.

    Returns:
        Anzahl aktualisierter Zeilen.
    """
    async with get_db_session() as session:
        res = await session.execute(
            text(
                "SELECT DISTINCT karten_name FROM sammlung_alben "
                "WHERE kartentyp IS NULL AND karten_name != '__PLACEHOLDER__' "
                "LIMIT :limit"
            ),
            {"limit": limit},
        )
        namen = [r["karten_name"] for r in res.mappings().all()]

    if not namen:
        return 0

    try:
        treffer = await fetch_card_details_cached(namen)
    except Exception:
        logger.warning("Nachfüllen der Kartenmetadaten fehlgeschlagen", exc_info=True)
        return 0

    aktualisiert = 0
    async with get_db_session() as session:
        for name in namen:
            info = treffer.get(name.lower().strip())
            if not info:
                continue
            meta = karten_metadaten(info)
            res = await session.execute(
                text(
                    "UPDATE sammlung_alben SET edition = :edition, seltenheit = :seltenheit, "
                    "farben = :farben, manakosten = :manakosten, kartentyp = :kartentyp "
                    "WHERE karten_name = :name AND kartentyp IS NULL"
                ),
                {**meta, "name": name},
            )
            aktualisiert += res.rowcount or 0
    return aktualisiert


# ======================================================================
# Lokale Request Models (zur Kompatibilität mit originalen Signaturen)
# ======================================================================
class DeleteKarteData(BaseModel):
    karten_id: int

class DeleteAlbumData(BaseModel):
    benutzername: str
    album_name: str

class KartenWunsch(BaseModel):
    """Eine ausgewählte Karte, wahlweise mit Wunschanzahl."""
    name: str
    # None heisst "alles, was von dieser Karte fehlt" -- dasselbe wie ein
    # blosser Name in der Liste.
    anzahl: Optional[int] = None


class DeckUebernahmeData(BaseModel):
    """Fehlende Karten eines Decks in die Sammlung übernehmen."""
    deck_id: int
    album_name: str = ""
    # Standardländer sind vom Deckbau her beliebig austauschbar und werden von
    # den wenigsten Spielern einzeln erfasst -- deshalb standardmässig aus.
    mit_standardlaendern: bool = False
    # Auswahl einzelner Karten. Leer oder nicht gesetzt heisst: alle fehlenden.
    #
    # Zwei Schreibweisen, damit ein blosser Name weiterhin "alles, was von
    # dieser Karte fehlt" bedeutet:
    #     ["Sol Ring"]                          -> alle fehlenden Exemplare
    #     [{"name": "Sol Ring", "anzahl": 2}]   -> hoechstens zwei
    #
    # Die Anzahl ist ein WUNSCH, keine Anweisung: der Server deckelt sie auf
    # das, was wirklich fehlt (services/bestand.fehlende_exemplare). Mehr als
    # fehlt wird nie angelegt -- sonst koennte eine veraenderte Anfrage die
    # Sammlung aufblaehen, und zweimal Druecken wuerde den Bestand verdoppeln.
    #
    # Die Obergrenze schützt davor, dass jemand eine Liste mit hunderttausend
    # Einträgen schickt und damit den Vergleich unnötig lange laufen lässt.
    nur_karten: Optional[List[Union[str, KartenWunsch]]] = Field(default=None, max_length=500)


class AddKarteData(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str
    bild_url: str = ""
    preis: str = "0.00"
    # Standard ist die normale Ausführung -- sie ist die häufigere, und eine
    # falsch als Foil geführte Karte würde den Sammlungswert nach oben
    # verfälschen. Bestehende Einträge gelten aus demselben Grund als nicht Foil.
    foil: bool = False
    # Sprache der physischen Karte ("en", "de", ...). Leer bedeutet
    # "nicht angegeben" und wird auch so gespeichert, statt Englisch zu raten.
    sprache: str = ""
    # Der besessene Druck. Ohne diese Angaben wurde immer der Standarddruck
    # angesetzt -- bei alten Karten weicht dessen Preis um ein Vielfaches ab.
    scryfall_id: str = ""
    edition: str = ""
    sammlernummer: str = ""
    # Zustand nach der üblichen Skala. Leer heisst "nicht angegeben".
    zustand: str = ""

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
@limiter.limit("10/minute")
async def get_sammlung(benutzername: str, request: Request, current_user: str = Depends(get_current_user)):
    """Die vollstaendige Sammlung in einer Antwort.

    Die Oberflaeche ruft das nicht mehr auf: sie laedt die Ordneruebersicht
    (/uebersicht) und dann seitenweise (/filter). Bei 15000 Karten sind das
    25 KB statt 4,5 MB.

    Der Endpunkt bleibt trotzdem bestehen -- er ist Teil der Schnittstelle,
    und wer die Sammlung am Stueck braucht (eigenes Skript, Datenauszug),
    soll das weiterhin koennen. Er blockiert dabei niemanden mehr, siehe
    services/antwort.py.
    """
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    # Die DB-Session wird bewusst VOR dem Scryfall-Abruf wieder freigegeben.
    # Vorher blieb die Verbindung während des (langsamen) Netzwerk-Calls belegt --
    # bei vielen gleichzeitigen Nutzern erschöpft das den Verbindungspool und
    # blockiert andere Anfragen wie den Login.
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
            {"name": current_user}
        )
        rows = res.mappings().all()

    echte = [r for r in rows if r["karten_name"] != "__PLACEHOLDER__"]
    daten_je_zeile = await kartendaten_fuer_zeilen(echte)

    # Zusammenbauen UND Verpacken laufen in einem eigenen Thread. Beides ist
    # reine Rechenarbeit, und im Ereignisschleifen-Faden blockiert sie ALLE
    # anderen Anfragen: während eine Sammlung mit 15000 Karten geladen wurde,
    # brauchte ein einfacher /health-Aufruf bis zu 472 ms. Danach 117 ms.
    #
    # Das Verpacken gehört ausdrücklich dazu -- es war sogar der grössere
    # Anteil. Würde hier ein dict zurückgegeben, liefe FastAPIs
    # jsonable_encoder (295 ms) plus json.dumps (113 ms) wieder in der
    # Ereignisschleife und der Gewinn wäre dahin. Siehe services/antwort.py.
    return await asyncio.to_thread(_sammlung_antwort, rows, daten_je_zeile)


def _sammlung_antwort(rows, daten_je_zeile) -> Response:
    return json_antwort({"erfolg": True, "alben": _alben_aufbauen(rows, daten_je_zeile)})


# ======================================================================
# GET /api/sammlung/{benutzername}/uebersicht – Ordner ohne die Karten
# ======================================================================
# Anzahl Vorschaukarten je Ordner. Die Ordnerkachel zeigt vier Bilder --
# mehr zu senden waere Ballast, weniger wuerde die Kachel aendern.
VORSCHAU_KARTEN = 4


def _uebersicht_bauen(rows, daten_je_zeile) -> Dict[str, Any]:
    """Je Ordner: Anzahl, Wert und die vier wertvollsten Karten als Vorschau.

    Die Ordneruebersicht brauchte bisher die vollstaendige Sammlung, nur um im
    Browser Summen zu bilden und vier Vorschaubilder auszuwaehlen. Bei 15000
    Karten waren das 4,5 MB, die der Browser laden, entpacken und behalten
    musste -- fuer eine Ansicht, die keine einzige davon zeigt.

    Gerechnet wird hier dasselbe wie vorher im Browser (siehe preis_zahl),
    uebertragen werden aber nur die Ergebnisse.
    """
    je_album: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        # Platzhalterzeilen halten leere Ordner am Leben, sind aber keine
        # Karten. Das Frontend hat sie bisher herausgefiltert -- jetzt hier,
        # sonst zaehlt ein leerer Ordner ploetzlich eine Karte.
        if row["karten_name"] == "__PLACEHOLDER__":
            je_album.setdefault(row["album_name"], [])
            continue
        je_album.setdefault(row["album_name"], []).append(
            karte_aus_zeile(row, daten_je_zeile.get(row["id"])))

    alben = []
    gesamtwert = 0.0
    wunschliste = {"anzahl": 0, "wert": 0.0}
    for name, karten in je_album.items():
        wert = sum(karten_preis(k) for k in karten)
        if name == "Wunschliste":
            # Die Wunschliste ist kein Besitz und zaehlt nicht zum
            # Sammlungswert -- das Frontend hat sie ebenfalls herausgerechnet.
            wunschliste = {"anzahl": len(karten), "wert": round(wert, 2)}
            continue
        gesamtwert += wert
        alben.append({
            "name": name,
            "anzahl": len(karten),
            "wert": round(wert, 2),
            "vorschau": sorted(karten, key=karten_preis,
                               reverse=True)[:VORSCHAU_KARTEN],
        })

    return {"erfolg": True, "alben": alben, "gesamtwert": round(gesamtwert, 2),
            "wunschliste": wunschliste}


@router.get(
    "/sammlung/{benutzername}/uebersicht",
    summary="Ordneruebersicht ohne die einzelnen Karten",
)
@limiter.limit("120/minute")
async def sammlung_uebersicht(benutzername: str, request: Request,
                              current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403,
                            detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name"),
            {"name": current_user})
        rows = res.mappings().all()

    echte = [r for r in rows if r["karten_name"] != "__PLACEHOLDER__"]
    daten_je_zeile = await kartendaten_fuer_zeilen(echte)
    return await asyncio.to_thread(_uebersicht_antwort, rows, daten_je_zeile)


def _uebersicht_antwort(rows, daten_je_zeile) -> Response:
    return json_antwort(_uebersicht_bauen(rows, daten_je_zeile))


# ======================================================================
# GET /api/sammlung/{benutzername}/top – die wertvollsten Karten
# ======================================================================
MAX_TOP = 50


@router.get(
    "/sammlung/{benutzername}/top",
    summary="Die wertvollsten Karten der Sammlung",
)
@limiter.limit("60/minute")
async def sammlung_top(benutzername: str, request: Request,
                       limit: int = Query(default=10, ge=1, le=MAX_TOP),
                       current_user: str = Depends(get_current_user)):
    """Fuer "Top 10 Wertvollste Karten".

    Vorher lud das Frontend dafuer die gesamte Sammlung und sortierte sie im
    Browser -- 15000 Karten, um zehn anzuzeigen. Sortiert wird weiterhin ueber
    alle Zeilen, denn der Live-Preis steht nicht in der Datenbank; uebertragen
    werden aber nur die zehn.
    """
    if benutzername != current_user:
        raise HTTPException(status_code=403,
                            detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM sammlung_alben WHERE benutzername = :name "
                 "AND album_name != 'Wunschliste' AND karten_name != '__PLACEHOLDER__'"),
            {"name": current_user})
        rows = res.mappings().all()

    daten_je_zeile = await kartendaten_fuer_zeilen(rows)
    return await asyncio.to_thread(_top_antwort, rows, daten_je_zeile, limit)


def _top_antwort(rows, daten_je_zeile, limit: int) -> Response:
    karten = []
    for row in rows:
        karte = karte_aus_zeile(row, daten_je_zeile.get(row["id"]))
        karte["albumName"] = row["album_name"]
        karten.append(karte)
    karten.sort(key=karten_preis, reverse=True)
    return json_antwort({"erfolg": True, "karten": karten[:limit]})


# ======================================================================
# GET /api/sammlung/{benutzername}/alben – nur die Ordnernamen
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/alben",
    summary="Nur die Ordnernamen",
)
@limiter.limit("240/minute")
async def sammlung_albennamen(benutzername: str, request: Request,
                              current_user: str = Depends(get_current_user)):
    """Fuer Auswahlfelder ("In welchen Ordner legen?").

    Die Kartensuche hat dafuer die komplette Sammlung geladen und davon
    Object.keys() genommen -- 4,5 MB fuer eine Liste von Namen. Das hier ist
    reines SQL ohne Scryfall und ohne Zeilenschleife.
    """
    if benutzername != current_user:
        raise HTTPException(status_code=403,
                            detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT DISTINCT album_name FROM sammlung_alben "
                 "WHERE benutzername = :name ORDER BY album_name"),
            {"name": current_user})
        rows = res.mappings().all()
    return {"erfolg": True, "alben": [r["album_name"] for r in rows]}


# ======================================================================
# GET /api/sammlung/{benutzername}/kartennamen – Namen eines Ordners
# ======================================================================
@router.get(
    "/sammlung/{benutzername}/kartennamen",
    summary="Kartennamen eines Ordners",
)
@limiter.limit("60/minute")
async def sammlung_kartennamen(benutzername: str, request: Request,
                               album: str = Query(...),
                               current_user: str = Depends(get_current_user)):
    """Fuer den Synergie-Scanner, der nur die Namen braucht.

    Auch er lud bisher die vollstaendige Sammlung samt Bildern und Preisen,
    um daraus eine Namensliste zu bauen. Ohne Scryfall-Abfrage und ohne
    Preise bleibt davon ein Bruchteil uebrig.
    """
    if benutzername != current_user:
        raise HTTPException(status_code=403,
                            detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT karten_name FROM sammlung_alben "
                 "WHERE benutzername = :name AND album_name = :album "
                 "AND karten_name != '__PLACEHOLDER__'"),
            {"name": current_user, "album": album})
        rows = res.mappings().all()
    return {"erfolg": True, "namen": [r["karten_name"] for r in rows]}


def _gefilterte_karten(rows, daten_je_zeile, suche, farbe, seltenheit, edition,
                       manakosten_min, manakosten_max, typ) -> List[Dict[str, Any]]:
    """Wendet die Filter an und baut die Antwortliste. Reine Rechenarbeit."""
    result: List[Dict[str, Any]] = []
    for row in rows:
        # Vorrangig der gespeicherte Druck: Seltenheit und Edition
        # unterscheiden sich zwischen Auflagen, und gefiltert wird nach
        # dem, was tatsächlich im Ordner liegt.
        card_info = daten_je_zeile.get(row["id"])
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

        druck = druck_von(row)

        # Edition / Set -- die gespeicherte Auflage hat Vorrang.
        if edition:
            card_set = (druck["edition"] or card_info.get("set", "")).lower()
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

        # Dieselben Feldnamen wie ueberall sonst (karte_aus_zeile), erweitert
        # um das, was nur der Filter braucht.
        #
        # Vorher hatte diese Ansicht eigene Namen: "image_url" statt
        # "bild_url", "price" statt "livePreis", "originalPrice" statt
        # "preis". Zwei Formen fuer dieselbe Sache, und genau daran ist die
        # Preissortierung gescheitert -- sie las "livePreis", das es hier
        # nicht gab, bekam fuer jede Karte 0 und tat schlicht nichts.
        karte = karte_aus_zeile(row, card_info)
        karte.update({
            # Der Anzeigename kommt von Scryfall: er ist korrekt geschrieben,
            # auch wenn die Zeile mit Tippfehler gespeichert wurde.
            "name": card_info.get("name", row["karten_name"]),
            "type": card_info.get("type", ""),
            "colors": card_info.get("colors", []),
            "cmc": card_info.get("cmc", 0),
            "rarity": card_info.get("rarity", ""),
            # "set" faellt auf die Angabe von Scryfall zurueck, "edition" ist
            # ausschliesslich der gespeicherte Druck -- beides wird gebraucht.
            "set": (druck["edition"] or card_info.get("set", "")),
            "album_name": row["album_name"],
        })
        result.append(karte)

    return result


# ----------------------------------------------------------------------
# Sortierung
# ----------------------------------------------------------------------
# Muss auf dem Server passieren, seit seitenweise geladen wird. Sortierte der
# Browser nur das Geladene, hiesse "teuerste zuerst" in Wahrheit "die teuerste
# der ersten 100" -- eine Angabe, die falsch ist, ohne falsch auszusehen.
SORTIERUNGEN = ("name", "priceDesc", "priceAsc", "cmc", "rarity")

# Seltenheit hat keine natuerliche Ordnung -- dieselben Gewichte wie bisher
# im Browser, damit sich die Reihenfolge nicht aendert.
_SELTENHEIT_GEWICHT = {"mythic": 4, "rare": 3, "uncommon": 2, "common": 1}

# Was localeCompare zusammenzieht, Pythons Standardvergleich aber trennt.
# Ohne das landet "Ætherling" hinter "Zur" statt bei "Ae", und "Jötun" hinter
# allen ASCII-Namen. Beides kommt bei Magic-Karten wirklich vor.
_LIGATUREN = str.maketrans({
    "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "ß": "ss",
    "Ø": "O", "ø": "o", "Þ": "TH", "þ": "th", "Đ": "D", "đ": "d",
})


def sortierschluessel_name(name: Optional[str]) -> tuple:
    """Namensschluessel, der sich wie localeCompare im Browser verhaelt.

    Akzente werden zum Grundbuchstaben zusammengezogen ("Jötun" bei "Jo"),
    Gross-/Kleinschreibung spielt keine Rolle. Der Originalname steht als
    zweiter Teil im Schluessel, damit die Reihenfolge bei gleichem Grundwort
    trotzdem eindeutig ist -- sonst haengt sie vom Zufall der Zeilenfolge ab
    und eine Seite koennte dieselbe Karte zweimal zeigen.
    """
    roh = name or ""
    zerlegt = unicodedata.normalize("NFKD", roh.translate(_LIGATUREN))
    ohne_akzente = "".join(z for z in zerlegt if not unicodedata.combining(z))
    return (ohne_akzente.casefold(), roh)


def sortiere_karten(karten: List[Dict[str, Any]], sortierung: str) -> List[Dict[str, Any]]:
    """Sortiert die gefilterte Liste. Gleiche Regeln wie vorher im Browser.

    Der Preis kommt aus "livePreis" -- dem Feld, das jede aufbereitete Karte
    traegt. Der Browser las frueher genau dieses Feld, bekam es vom Filter
    aber nicht geliefert (dort hiess es "price") und rechnete deshalb mit 0:
    "nach Preis sortieren" hat in der Ordneransicht nie etwas getan. Beide
    Namen zu akzeptieren waere ein Pflaster; stattdessen liefert der Filter
    jetzt dieselben Felder wie alle anderen Ansichten.
    """
    def preis(k):
        return karten_preis(k)

    if sortierung == "priceDesc":
        return sorted(karten, key=lambda k: (-preis(k), sortierschluessel_name(k.get("name"))))
    if sortierung == "priceAsc":
        return sorted(karten, key=lambda k: (preis(k), sortierschluessel_name(k.get("name"))))
    if sortierung == "cmc":
        return sorted(karten, key=lambda k: (preis_zahl(k.get("cmc") or 0),
                                             sortierschluessel_name(k.get("name"))))
    if sortierung == "rarity":
        return sorted(karten, key=lambda k: (
            -_SELTENHEIT_GEWICHT.get(str(k.get("rarity") or "").lower(), 0),
            sortierschluessel_name(k.get("name"))))
    return sorted(karten, key=lambda k: sortierschluessel_name(k.get("name")))


def _filter_antwort(rows, daten_je_zeile, suche, farbe, seltenheit, edition,
                    manakosten_min, manakosten_max, typ,
                    seite: int, pro_seite: int, sortierung: str) -> Response:
    """Filtert, sortiert, schneidet die gewuenschte Seite heraus und verpackt.

    Gefiltert und sortiert wird ueber ALLE Zeilen, erst danach wird
    geschnitten. Andersherum (in SQL blaettern, dann filtern) waere schneller,
    aber falsch: die Filter laufen teils in Python -- eine Seite haette dann
    mal 40, mal 90 Treffer, und die Gesamtzahl waere geraten. Lieber ehrlich
    zaehlen.
    """
    karten = _gefilterte_karten(rows, daten_je_zeile, suche, farbe, seltenheit,
                                edition, manakosten_min, manakosten_max, typ)
    karten = sortiere_karten(karten, sortierung)
    anfang = (seite - 1) * pro_seite
    return json_antwort({
        "erfolg": True,
        "karten": karten[anfang:anfang + pro_seite],
        "gesamt": len(karten),
        "seite": seite,
        "pro_seite": pro_seite,
        "sortierung": sortierung,
    })


# Karten je Seite in der Ordneransicht. 100 fuellt einen Bildschirm mehrfach,
# bleibt aber weit unter der Groesse, ab der das Rendern im Browser ruckelt.
# Die Obergrenze schuetzt davor, dass jemand mit ?pro_seite=999999 doch wieder
# die ganze Sammlung in einem Stueck anfordert.
# Grösste CSV-Datei, die der Import annimmt. Eine Sammlung mit 100.000 Karten
# liegt bei etwa 5 MB -- 10 MB sind also reichlich, und alles darüber ist
# entweder ein Versehen oder ein Angriff.
MAX_CSV_BYTES = 10 * 1024 * 1024

STANDARD_PRO_SEITE = 100
MAX_PRO_SEITE = 500

# Wie viele Zeilen ohne gespeicherte Edition höchstens über den Namen
# aufgelöst werden. Das betrifft nur Altbestände; die Wartungsaufgabe füllt
# die Spalte nach, danach ist die Liste vollständig ohne einen einzigen
# Scryfall-Aufruf. Die Grenze verhindert, dass eine grosse, noch nicht
# nachgefüllte Sammlung den Filterbereich ausbremst.
MAX_EDITION_RUECKFALL = 300

# Führende Zahl wie parseFloat sie liest: "1.50 €" -> 1.50, "abc" -> nichts.
_ZAHL_AM_ANFANG = re.compile(r"^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def preis_zahl(wert) -> float:
    """Preis als Zahl -- genau so, wie der Browser ihn bisher gelesen hat.

    Die Summen (Ordnerwert, Gesamtwert) wurden bislang im Frontend gebildet:

        parseFloat(String(livePreis || preis || "0").replace(',', '.')) || 0

    Jetzt rechnet der Server. Damit dem Nutzer nicht plötzlich ein anderer
    Sammlungswert angezeigt wird, muss hier dasselbe herauskommen -- auch in
    den Randfällen. Deshalb nicht einfach float():

    * float("1.50 €") wirft, parseFloat liest 1.50.
    * float("") wirft, parseFloat liefert NaN -- und "|| 0" macht daraus 0.
    * String.replace(",", ".") ersetzt nur das ERSTE Komma. "1,234,56" wird
      damit zu "1.234,56" und parseFloat liest 1.234. Nachgebaut, nicht
      korrigiert: eine "Verbesserung" hier würde stillschweigend andere
      Summen ergeben als die, die der Nutzer bisher gesehen hat.
    """
    if isinstance(wert, bool):
        return 0.0
    if isinstance(wert, (int, float)):
        return 0.0 if wert != wert else float(wert)  # NaN -> 0
    if wert is None:
        return 0.0
    treffer = _ZAHL_AM_ANFANG.match(str(wert).replace(",", ".", 1))
    if not treffer:
        return 0.0
    try:
        zahl = float(treffer.group(0))
    except ValueError:
        return 0.0
    return 0.0 if zahl != zahl else zahl


def karten_preis(karte: Dict[str, Any]) -> float:
    """Wert einer aufbereiteten Karte -- livePreis, sonst preis, sonst 0."""
    return preis_zahl(karte.get("livePreis") or karte.get("preis") or 0)


def karte_aus_zeile(row, card_info) -> Dict[str, Any]:
    """Eine Sammlungszeile in die Form, die das Frontend anzeigt.

    Bewusst EINE Stelle: Übersicht, Top-Liste und Albenansicht zeigen dieselbe
    Karte. Lägen die Felder mehrfach herum, wiche früher oder später eine
    Ansicht ab -- etwa beim Foil-Preis, der genau so schon einmal falsch war.
    """
    druck = druck_von(row)
    return {
        "id": row["id"],
        "name": row["karten_name"],
        "bild_url": (card_info.get("image", row["bild_url"]) if card_info
                     else row["bild_url"]),
        "preis": row["preis"],
        "livePreis": live_preis_fuer(card_info, row, row["preis"]),
        "foil": ist_foil(row),
        "sprache": sprache_von(row),
        "zustand": zustand_von(row),
        "edition": druck["edition"],
        "sammlernummer": druck["sammlernummer"],
        "edition_name": (card_info or {}).get("set_name"),
    }


def _alben_aufbauen(rows, daten_je_zeile) -> Dict[str, List[Dict[str, Any]]]:
    """Baut die Albenstruktur aus den Zeilen. Reine Rechenarbeit, kein Warten --
    deshalb läuft sie ausserhalb der Ereignisschleife."""
    alben: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        album = row["album_name"]
        if album not in alben:
            alben[album] = []
        alben[album].append(karte_aus_zeile(row, daten_je_zeile.get(row["id"])))
    return alben


# ======================================================================
# POST /api/sammlung/hinzufuegen – Karte hinzufügen
# ======================================================================
@router.post(
    "/sammlung/hinzufuegen",
    summary="Karte zur Sammlung hinzufügen",
)
@limiter.limit("240/minute")
async def add_karte(data: AddKarteData, request: Request, current_user: str = Depends(get_current_user)):
    # Strukturierte Metadaten gleich mitschreiben. Der Aufruf ist praktisch
    # gratis: die Karte wurde soeben gesucht und liegt daher im Cache. Der
    # Platzhalter für leere Alben wird bewusst nicht aufgelöst.
    card_info = None
    if data.karten_name and data.karten_name != "__PLACEHOLDER__":
        # Der ausgewählte Druck hat Vorrang: nur er sagt, WELCHE Auflage im
        # Ordner liegt. Über den Namen käme immer der Standarddruck -- und
        # damit dessen Preis, der bei alten Karten um ein Vielfaches abweicht.
        if data.scryfall_id:
            try:
                card_info = await druck_nach_id(data.scryfall_id)
            except Exception:
                logger.warning("Druck %r nicht auflösbar", data.scryfall_id, exc_info=True)
        if not card_info:
            try:
                treffer = await fetch_card_details_cached([data.karten_name])
                card_info = treffer.get(data.karten_name.lower().strip())
            except Exception:
                logger.warning("Kartenmetadaten für %r nicht auflösbar", data.karten_name, exc_info=True)

    meta = karten_metadaten(card_info)
    # Angaben des Clients gehen vor, wo sie den Druck genauer beschreiben als
    # der aufgelöste Datensatz -- er hat die Auflage schliesslich ausgewählt.
    if data.edition.strip():
        meta["edition"] = data.edition.strip().lower()

    # Preis passend zur Ausführung festhalten. Übergibt der Client keinen
    # (oder den Normalpreis für eine Foil-Karte), wird er hier korrigiert --
    # sonst stünde eine Foil-Karte mit dem deutlich niedrigeren Normalpreis in
    # der Sammlung.
    preis = data.preis
    if card_info:
        passend = preis_fuer_variante(card_info.get("prices") or {}, foil=data.foil)
        if passend:
            preis = passend

    zustand = (data.zustand or "").strip().upper()
    if zustand and zustand not in ZUSTAENDE:
        raise HTTPException(status_code=400, detail=f"Unbekannter Zustand: {data.zustand}")

    async with get_db_session() as session:
        await session.execute(
            text(_SAMMLUNG_INSERT_SQL),
            {"user": current_user, "name": data.karten_name, "album": data.album_name,
             "url": data.bild_url, "price": preis, "foil": bool(data.foil),
             "sprache": (data.sprache or "").strip().lower() or None,
             # NUR wenn der Client eine Auflage ausgewählt hat. Sonst bliebe
             # hier die Kennung des Standarddrucks stehen -- eine Behauptung
             # darüber, welches Exemplar jemand besitzt, die niemand aufgestellt
             # hat. Ohne Kennung greift bei der Bewertung der Standarddruck,
             # und das ist als Näherung erkennbar.
             "scryfall_id": data.scryfall_id.strip() or None,
             "sammlernummer": (data.sammlernummer.strip()
                               or (card_info or {}).get("sammlernummer")
                               if data.scryfall_id.strip() else None) or None,
             "zustand": zustand or None,
             **meta}
        )
    return {"erfolg": True}

# ======================================================================
# POST /api/sammlung/aus-deck – fehlende Deckkarten übernehmen
# ======================================================================
# Obergrenze pro Aufruf. Ein Deck hat höchstens 100 Karten; alles darüber wäre
# ein Fehler in der Liste und soll die Datenbank nicht mit tausenden Zeilen
# fluten.
MAX_UEBERNAHME = 250


@router.post(
    "/sammlung/aus-deck",
    summary="Fehlende Karten eines Decks in die Sammlung übernehmen",
)
@limiter.limit("30/minute")
async def sammlung_aus_deck(data: DeckUebernahmeData, request: Request, current_user: str = Depends(get_current_user)):
    """Legt die Exemplare an, die dem Deck in der Sammlung noch fehlen.

    Bewusst nur die fehlenden: zweimal Drücken ändert beim zweiten Mal nichts.
    Ein "alle Karten übernehmen" würde die Sammlung bei jedem Druck verdoppeln.

    Gerechnet wird mit demselben Modul wie die Anzeige "was fehlt dir noch" --
    sonst würde hier etwas anderes angelegt, als danebensteht.
    """
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT id, name, liste, benutzername FROM decks WHERE id = :id"),
            {"id": data.deck_id},
        )
        deck = res.mappings().first()

    if not deck:
        raise HTTPException(status_code=404, detail="Deck nicht gefunden.")
    if deck["benutzername"] != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Deck.")

    parsed = parse_decklist(deck["liste"] or "")
    if not parsed:
        return {"erfolg": True, "hinzugefuegt": 0, "album": data.album_name or deck["name"],
                "uebersprungene_standardlaender": 0, "abgeschnitten": 0}

    async with get_db_session() as session:
        res = await session.execute(
            text(
                "SELECT karten_name, COUNT(*) AS anzahl FROM sammlung_alben "
                "WHERE benutzername = :user AND karten_name != '__PLACEHOLDER__' "
                "GROUP BY karten_name"
            ),
            {"user": current_user},
        )
        bestand = bestand_aus_zeilen(res.mappings().all())

    scryfall_data = await fetch_card_details_cached(list({p["name"] for p in parsed}))
    # Mit den Auflagen der Deckliste: die Übernahme muss dieselbe Rechnung
    # aufmachen wie der Abgleich daneben, sonst legt der Knopf etwas anderes an,
    # als in der Liste steht.
    bedarf = bedarf_aus_deck(parsed, scryfall_data, await drucke_fuer_deck(parsed))
    # Eine LEERE Auswahl ist etwas anderes als gar keine: "nichts angekreuzt"
    # muss nichts anlegen, nicht alles. Deshalb wird auf None geprüft und
    # nicht auf Wahrheitswert -- sonst würde eine leere Liste stillschweigend
    # zu "alle fehlenden Karten".
    nur_namen = None
    mengen: Dict[str, int] = {}
    if data.nur_karten is not None:
        nur_namen = []
        for eintrag in data.nur_karten:
            if isinstance(eintrag, str):
                nur_namen.append(eintrag)
            else:
                nur_namen.append(eintrag.name)
                if eintrag.anzahl is not None:
                    mengen[eintrag.name] = eintrag.anzahl

    plan = fehlende_exemplare(bedarf, bestand,
                              mit_standardlaendern=data.mit_standardlaendern,
                              grenze=MAX_UEBERNAHME,
                              nur_namen=nur_namen,
                              mengen=mengen)

    album = (data.album_name or "").strip() or deck["name"]

    zeilen = []
    for posten in plan["posten"]:
        info = posten.get("info")
        meta = karten_metadaten(info)
        preis = preis_fuer_variante((info or {}).get("prices") or {}, foil=False) or posten["preis"]
        for _ in range(posten["anzahl"]):
            zeilen.append({
                "user": current_user,
                "name": posten["name"],
                "album": album,
                "url": posten["bild"],
                "price": str(preis),
                # Ausführung, Sprache, Auflage und Zustand kennt eine
                # Deckliste nicht -- alles bleibt offen, statt "normal,
                # englisch, Near Mint" zu unterstellen. Die Preisangabe stammt
                # vom Standarddruck und ist als Näherung gekennzeichnet, indem
                # keine Druck-Kennung gespeichert wird.
                "foil": False,
                "sprache": None,
                "scryfall_id": None,
                "sammlernummer": None,
                "zustand": None,
                **meta,
            })

    if zeilen:
        async with get_db_session() as session:
            await session.execute(text(_SAMMLUNG_INSERT_SQL), zeilen)

    return {
        "erfolg": True,
        "hinzugefuegt": len(zeilen),
        "album": album,
        "uebersprungene_standardlaender": plan["uebersprungene_standardlaender"],
        "abgeschnitten": plan["abgeschnitten"],
    }


# ======================================================================
# POST /api/sammlung/loeschen – Karte entfernen
# ======================================================================
@router.post(
    "/sammlung/loeschen",
    summary="Karte aus Sammlung löschen",
)
@limiter.limit("240/minute")
async def delete_karte(data: DeleteKarteData, request: Request, current_user: str = Depends(get_current_user)):
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
@limiter.limit("30/minute")
async def delete_album(data: DeleteAlbumData, request: Request, current_user: str = Depends(get_current_user)):
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
@limiter.limit("120/minute")
async def sammlung_filter(
    benutzername: str,
    request: Request,
    farbe: str = Query(default=None, description="Farbe (W, U, B, R, G)"),
    seltenheit: str = Query(default=None, description="Seltenheit (common, uncommon, rare, mythic)"),
    edition: str = Query(default=None, description="Edition / Set-Code"),
    manakosten_min: int = Query(default=None, description="Minimale Manakosten (CMC)"),
    manakosten_max: int = Query(default=None, description="Maximale Manakosten (CMC)"),
    typ: str = Query(default=None, description="Kartentyp (Creature, Instant, Sorcery, ...)"),
    suche: str = Query(default=None, description="Freitextsuche im Kartennamen"),
    album: str = Query(default=None, description="Filter nach Albumname"),
    seite: int = Query(default=1, ge=1, description="Seitenzahl, beginnend bei 1"),
    pro_seite: int = Query(default=STANDARD_PRO_SEITE, ge=1, le=MAX_PRO_SEITE,
                           description="Karten je Seite"),
    sortierung: str = Query(default="name",
                            description="name, priceDesc, priceAsc, cmc oder rarity"),
    current_user: str = Depends(get_current_user),
):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    try:
        # SQL-Vorfilterung auf den strukturierten Spalten. Jede Bedingung lässt
        # Zeilen mit NULL bewusst durch: Alt-Zeilen aus der Zeit vor dem
        # Befüllen der Spalten würden sonst aus den Ergebnissen verschwinden.
        # Sie werden anschließend wie bisher in Python geprüft -- die
        # Korrektheit bleibt also unverändert, nur die Datenmenge sinkt.
        bedingungen = ["benutzername = :name"]
        params: Dict[str, Any] = {"name": current_user}

        if album:
            bedingungen.append("album_name = :album")
            params["album"] = album
        else:
            bedingungen.append("album_name != 'Wunschliste'")

        if seltenheit:
            bedingungen.append("(seltenheit IS NULL OR LOWER(seltenheit) = :f_seltenheit)")
            params["f_seltenheit"] = seltenheit.lower()
        if edition:
            bedingungen.append("(edition IS NULL OR LOWER(edition) = :f_edition)")
            params["f_edition"] = edition.lower()
        if farbe:
            bedingungen.append("(farben IS NULL OR farben LIKE :f_farbe)")
            params["f_farbe"] = f"%{farbe.upper()}%"
        if typ:
            bedingungen.append("(kartentyp IS NULL OR LOWER(kartentyp) LIKE :f_typ)")
            params["f_typ"] = f"%{typ.lower()}%"
        if manakosten_min is not None:
            bedingungen.append("(manakosten IS NULL OR manakosten >= :f_cmc_min)")
            params["f_cmc_min"] = manakosten_min
        if manakosten_max is not None:
            bedingungen.append("(manakosten IS NULL OR manakosten <= :f_cmc_max)")
            params["f_cmc_max"] = manakosten_max

        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM sammlung_alben WHERE " + " AND ".join(bedingungen)),
                params,
            )
            rows = res.mappings().all()

        if not rows:
            return {"erfolg": True, "karten": []}

        daten_je_zeile = await kartendaten_fuer_zeilen(rows)

        # Filtern, Zusammenbauen und Verpacken sind reine Rechenarbeit --
        # ausserhalb der Ereignisschleife, damit eine grosse Sammlung nicht
        # alle anderen Anfragen anhält (siehe _sammlung_antwort).
        return await asyncio.to_thread(
            _filter_antwort, rows, daten_je_zeile,
            suche, farbe, seltenheit, edition, manakosten_min, manakosten_max, typ,
            seite, pro_seite,
            # Ein unbekannter Wert faellt auf die Namenssortierung zurueck
            # statt die Anfrage abzulehnen: eine veraltete Lesezeichen-URL
            # soll die Ansicht nicht kaputtmachen.
            sortierung if sortierung in SORTIERUNGEN else "name")
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
@limiter.limit("120/minute")
async def sammlung_editions(benutzername: str, request: Request, album: str = Query(default=None), current_user: str = Depends(get_current_user)):
    """Die Editionen, die tatsächlich in der Sammlung liegen.

    Vorher wurde für JEDEN eindeutigen Kartennamen der Standarddruck bei
    Scryfall aufgelöst und dessen Edition genommen. Das war doppelt falsch:

    * Zu langsam. Der Filterbereich ruft das bei jedem Ordnerwechsel auf, und
      es waren so viele Auflösungen wie eindeutige Kartennamen -- bei einer
      grossen Sammlung tausende.
    * Zu ungenau. Wer eine alte Auflage besitzt, hat sie hier nicht gefunden:
      angezeigt wurde die Edition des NEUESTEN Nachdrucks. Der Filter selbst
      geht dagegen vom gespeicherten Druck aus -- die Auswahlliste passte also
      nicht zu dem, wonach gefiltert wird.

    Jetzt beantwortet die gespeicherte Spalte die Frage. Für den Klarnamen der
    Edition genügt EIN Druck je Edition statt einer je Karte.
    """
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    try:
        bedingungen = ["benutzername = :name"]
        params: Dict[str, Any] = {"name": current_user}
        if album:
            bedingungen.append("album_name = :album")
            params["album"] = album
        wo = " AND ".join(bedingungen)

        async with get_db_session() as session:
            # Je Edition ein Beispieldruck -- daraus kommt der Klarname.
            res = await session.execute(
                text(f"SELECT edition, MAX(scryfall_id) AS kennung FROM sammlung_alben "
                     f"WHERE {wo} AND edition IS NOT NULL AND edition != '' "
                     f"GROUP BY edition"),
                params)
            gruppen = res.mappings().all()

            # Zeilen aus der Zeit vor der Spalte haben keine Edition. Ohne sie
            # verschwänden Altbestände aus der Auswahl, bis die Wartungsaufgabe
            # sie nachgefüllt hat.
            res = await session.execute(
                text(f"SELECT DISTINCT karten_name FROM sammlung_alben "
                     f"WHERE {wo} AND (edition IS NULL OR edition = '') "
                     f"AND karten_name != '__PLACEHOLDER__' "
                     f"LIMIT {MAX_EDITION_RUECKFALL}"),
                params)
            ohne_edition = [z["karten_name"] for z in res.mappings().all()]

        editionen: Dict[str, str] = {}

        kennungen = [g["kennung"] for g in gruppen if g["kennung"]]
        drucke = await druecke_nach_ids(kennungen) if kennungen else {}
        namen_je_code = {(d.get("set") or "").lower(): d.get("set_name")
                         for d in drucke.values() if d.get("set")}

        for gruppe in gruppen:
            code = (gruppe["edition"] or "").lower()
            if not code:
                continue
            # Ist kein Klarname auflösbar, steht der Code da. Einen Namen zu
            # erfinden wäre schlechter als die Abkürzung.
            editionen[code] = namen_je_code.get(code) or code.upper()

        if ohne_edition:
            nach_name = await fetch_card_details_cached(ohne_edition)
            for info in nach_name.values():
                code = (info.get("set") or "").lower()
                if code and code not in editionen:
                    editionen[code] = info.get("set_name") or code.upper()

        editions = [{"set_code": code, "set_name": name}
                    for code, name in editionen.items()]
        editions.sort(key=lambda e: e["set_name"])
        return {"erfolg": True, "editions": editions}
    except Exception as e:
        logger.exception("Fehler bei Editionen-Abfrage")
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# Asynchroner Background-Task für CSV-Import
# ======================================================================
def _is_implausible_card_name(name: str) -> bool:
    """
    Erkennt Zellinhalte, die offensichtlich KEIN Kartenname sind und beim
    Import niemals per Fuzzy-Suche 'erraten' werden dürfen (Scryfalls
    Fuzzy-Match löst z.B. den Set-Code 'SPM' auf die echte Karte 'Wispmare'
    auf -- so landete früher dieselbe fremde Karte in allen Alben):
    - rein numerische Werte (verrutschte Mengen-/Preis-Spalte, '1', '0.61')
    - kurze ALL-CAPS-Codes (Set-Codes wie 'SPM', 'ECL', 'MH2') -- echte
      Kartennamen sind nie komplett großgeschrieben
    """
    n = (name or "").strip()
    if not n:
        return True
    if re.fullmatch(r"[\d.,]+", n):
        return True
    if len(n) <= 5 and n.isupper() and n.isalnum():
        return True
    return False


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
            # Offensichtlichen Nicht-Kartennamen-Müll VOR dem Scryfall-Fetch
            # aussortieren, damit er nicht fuzzy auf fremde Karten auflöst.
            if _is_implausible_card_name(entry["name"]):
                failed += entry["anzahl"]
                errors_list.append(
                    f"Zeile {i}: '{entry['name']}' sieht nicht nach einem Kartennamen aus "
                    "(Zahl oder Set-Code) und wurde übersprungen."
                )
                continue
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
            
            meta = karten_metadaten(card_info)
            for _ in range(r["anzahl"]):
                rows_to_insert.append({
                    "user": benutzername,
                    "name": canonical_name,
                    "album": r["album"],
                    "url": bild_url,
                    "price": str(price_val),
                    # Nennt die Datei eine Foil-Spalte, wird sie übernommen;
                    # sonst gilt die Karte als normal. Das ist die sichere
                    # Annahme -- sie bewertet eher zu niedrig als zu hoch.
                    "foil": bool(r.get("foil")),
                    "sprache": (r.get("sprache") or "").strip().lower() or None,
                    # Der Import kennt die genaue Auflage nicht: eine
                    # Set-Angabe in der Datei ist ein Kürzel, keine Kennung
                    # eines bestimmten Drucks. Deshalb bleibt sie offen und der
                    # Preis stammt vom Standarddruck.
                    "scryfall_id": None,
                    "sammlernummer": None,
                    "zustand": None,
                    **meta,
                })
            imported += r["anzahl"]
            
        # 4. Insert into database
        if rows_to_insert:
            async with get_db_session() as session:
                await session.execute(text(_SAMMLUNG_INSERT_SQL), rows_to_insert)
                
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
@limiter.limit("10/minute")
async def sammlung_import_csv(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    album_name: str = Form("Import"),
    current_user: str = Depends(get_current_user),
):
    try:
        # In Stücken lesen und bei Überschreitung abbrechen. `await file.read()`
        # ohne Grenze zieht die GANZE Datei in den Arbeitsspeicher -- eine
        # einzige 2-GB-Datei genügt, um den Arbeitsprozess zu erschlagen, und
        # danach ist die Seite für ALLE weg. Die Drosselung (10/Minute) hilft
        # dagegen nicht: es braucht nur eine Anfrage.
        #
        # Der Text wird anschliessend noch an eine Hintergrundaufgabe
        # weitergereicht, liegt also doppelt im Speicher.
        brocken = []
        gelesen = 0
        while True:
            stueck = await file.read(64 * 1024)
            if not stueck:
                break
            gelesen += len(stueck)
            if gelesen > MAX_CSV_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(f"Die Datei ist grösser als "
                            f"{MAX_CSV_BYTES // (1024 * 1024)} MB. Teile sie bitte auf."))
            brocken.append(stueck)

        try:
            csv_text = b"".join(brocken).decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Die Datei ist keine UTF-8-Textdatei. Exportiere sie als CSV (UTF-8).")

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
    except HTTPException:
        # "Datei zu gross" und "keine UTF-8-Datei" sind Auskünfte an den
        # Nutzer, keine Programmfehler. Ohne dieses re-raise fängt der Block
        # unten sie ab und macht daraus HTTP 200 mit erfolg=False -- der
        # Browser sähe einen erfolgreichen Aufruf, und die Statusmeldung 413
        # käme nie an.
        raise
    except Exception as e:
        logger.exception("Fehler beim Starten des CSV-Imports")
        # str(e) gehört nicht zum Nutzer: bei einem Datenbankfehler steht dort
        # das SQL samt Tabellennamen.
        return {"erfolg": False,
                "error": "Der Import konnte nicht gestartet werden. Bitte versuche es erneut."}

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
@limiter.limit("10/minute")
async def sammlung_export_csv(benutzername: str, request: Request, current_user: str = Depends(get_current_user)):
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
            # Nach Ausführung getrennt: normale und Foil-Karten haben eigene
            # Preise und gehören im Export in eigene Zeilen.
            # Nach Auflage und Zustand getrennt: zwei Exemplare derselben
            # Karte aus verschiedenen Ausgaben sind nicht dasselbe und haben
            # unterschiedliche Preise.
            druck = druck_von(row)
            key = (row["karten_name"], row["album_name"], ist_foil(row), sprache_von(row) or "",
                   druck["edition"] or "", zustand_von(row) or "")
            if key not in aggregated:
                aggregated[key] = {"anzahl": 0, "preis": row["preis"], "foil": ist_foil(row),
                                   "zeile": row}
            aggregated[key]["anzahl"] += 1

        zeilen_fuer_daten = [w["zeile"] for w in aggregated.values()]
        daten_je_zeile = await kartendaten_fuer_zeilen(zeilen_fuer_daten) if zeilen_fuer_daten else {}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Kartenname", "Anzahl", "Edition", "Sammlernummer", "Album",
                         "Foil", "Sprache", "Zustand", "Preis_EUR"])

        for (karten_name, album_name, foil, sprache, edition, zustand), info in sorted(aggregated.items()):
            card_info = daten_je_zeile.get(info["zeile"]["id"], {})
            druck = druck_von(info["zeile"])
            edition_code = edition or card_info.get("set", "")
            price_eur = preis_fuer_variante(card_info.get("prices") or {}, foil=foil) or info["preis"]
            writer.writerow([
                card_info.get("name", karten_name),
                info["anzahl"],
                edition_code,
                druck["sammlernummer"] or "",
                album_name,
                "ja" if foil else "nein",
                sprache,
                zustand,
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
@limiter.limit("5/minute")
async def refresh_sammlung_prices(benutzername: str, request: Request, current_user: str = Depends(get_current_user)):
    if benutzername != current_user:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf die Sammlung dieses Benutzers.")
    is_premium = await check_user_premium(current_user)
    if not is_premium:
        return JSONResponse(
            status_code=403,
            content={"erfolg": False, "error": "Paywall: Dieses Feature steht nur Premium-Mitgliedern zur Verfügung."}
        )
    try:
        # 1. Karten des Benutzers holen -- mit der Kennung des besessenen
        #    Drucks, denn genau dessen Preis soll aufgefrischt werden.
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT DISTINCT karten_name, scryfall_id FROM sammlung_alben "
                     "WHERE benutzername = :name AND karten_name != '__PLACEHOLDER__'"),
                {"name": current_user}
            )
            rows = res.mappings().all()

        unique_names = list({row["karten_name"] for row in rows})
        # Über druck_von gelesen: fehlt die Spalte (Altbestand, Testdoppel),
        # soll die Auffrischung weiterlaufen statt mit einem Fehler abzubrechen.
        druck_ids = list({(druck_von(row)["scryfall_id"] or "") for row in rows} - {""})
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
        for kennung in druck_ids:
            scryfall_cache.delete(f"{DRUCK_CACHE_PRAEFIX}{kennung}")

        # 3. Frisch von Scryfall holen (schreibt es direkt neu in den Cache)
        await fetch_card_details_cached(unique_names)
        if druck_ids:
            await druecke_nach_ids(druck_ids)

        return {"erfolg": True}
    except Exception as e:
        logger.exception("Fehler bei refresh_sammlung_prices")
        return JSONResponse(status_code=500, content={"erfolg": False, "error": str(e)})

