"""
services/scryfall.py – Scryfall API-Client & Karten-Hilfsfunktionen

Kapselt alle Interaktionen mit der Scryfall API:
- fetch_card_details_cached(): Batch-Fetch für Kartenlisten mit Cache
- clean_card_name(): Bereinigt Kartennamen (Foil-Tags, Set-Codes, etc.)
- parse_decklist(): Parst Decklisten-Strings in strukturierte Daten
"""

import asyncio
import logging
import os
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Set

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

# Scryfalls Rate-Limit gilt PRO SERVER (IP), nicht pro Nutzer: bei 1000 Nutzern
# teilen sich alle dasselbe Budget von ~10 Anfragen/Sekunde. Deshalb wird der
# Zugriff hier GLOBAL gedrosselt statt mit lokalen Pausen pro Aufruf.
SCRYFALL_MAX_CONCURRENCY = int(os.getenv("SCRYFALL_MAX_CONCURRENCY", "4"))
SCRYFALL_MIN_INTERVAL = float(os.getenv("SCRYFALL_MIN_INTERVAL", "0.12"))  # ~8 req/s
SCRYFALL_COOLDOWN_SECONDS = float(os.getenv("SCRYFALL_COOLDOWN_SECONDS", "5"))
SCRYFALL_TIMEOUT = float(os.getenv("SCRYFALL_TIMEOUT", "8"))


class _ScryfallLimiter:
    """
    Prozessweite Zugriffskontrolle für die Scryfall-API.

    Drei Aufgaben:
    1. Begrenzt die Zahl GLEICHZEITIGER Anfragen (Semaphore).
    2. Vergibt Zeitslots mit Mindestabstand, sodass die Gesamtrate über alle
       Nutzer/Requests hinweg unter Scryfalls Limit bleibt.
    3. Merkt sich einen Cooldown nach einem 429 -- danach warten ALLE Aufrufer,
       statt weiter gegen die geschlossene Tür zu laufen (verhindert den
       Rückkopplungseffekt, bei dem Drosselung noch mehr Anfragen auslöst).
    """

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(SCRYFALL_MAX_CONCURRENCY)
        self._spacing_lock = asyncio.Lock()
        self._next_slot = 0.0
        self._cooldown_until = 0.0

    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    @property
    def under_pressure(self) -> bool:
        """True, solange Scryfall uns gerade drosselt."""
        try:
            return self._now() < self._cooldown_until
        except RuntimeError:  # kein laufender Event-Loop
            return False

    def note_rate_limited(self, seconds: Optional[float] = None) -> None:
        wait = seconds if (seconds and seconds > 0) else SCRYFALL_COOLDOWN_SECONDS
        wait = min(wait, 30.0)
        try:
            self._cooldown_until = max(self._cooldown_until, self._now() + wait)
        except RuntimeError:
            pass

    async def __aenter__(self):
        await self._sem.acquire()
        try:
            async with self._spacing_lock:
                now = self._now()
                start = max(now, self._next_slot, self._cooldown_until)
                self._next_slot = start + SCRYFALL_MIN_INTERVAL
            delay = start - self._now()
            if delay > 0:
                await asyncio.sleep(delay)
        except BaseException:
            self._sem.release()
            raise
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self._sem.release()
        return False


_limiter = _ScryfallLimiter()


def scryfall_client(**kwargs) -> httpx.AsyncClient:
    """httpx-Client mit dem von Scryfall geforderten User-Agent/Accept-Header.

    Das Timeout ist bewusst knapp: Ist Scryfall nicht erreichbar, soll die
    Anfrage schnell in die (begrenzte) Degradation laufen, statt Nutzer
    minutenlang auf einen hängenden Aufruf warten zu lassen.
    """
    kwargs.setdefault("headers", SCRYFALL_HEADERS)
    kwargs.setdefault("timeout", SCRYFALL_TIMEOUT)
    return httpx.AsyncClient(**kwargs)


async def scryfall_request(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> httpx.Response:
    """
    Führt eine Scryfall-Anfrage über die globale Drossel aus und wiederholt sie
    EINMAL bei HTTP 429. Das Warten übernimmt der Limiter (der Cooldown gilt für
    alle gleichzeitigen Aufrufer), nicht ein lokaler sleep.

    Gibt bei anhaltendem 429 die 429-Antwort zurück -- Aufrufer MÜSSEN das als
    "später erneut versuchen" behandeln, niemals als "Karte existiert nicht".
    """
    resp = None
    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            async with _limiter:
                resp = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            # Netzwerkaussetzer (Timeout, DNS, Verbindungsabbruch): EINMAL
            # wiederholen. Bewusst nur hier -- niemals durch Auffächern in
            # viele Einzelanfragen "kompensieren".
            last_error = exc
            if attempt == 0:
                logger.warning("Scryfall-Anfrage fehlgeschlagen (%s) -- ein Wiederholungsversuch.", type(exc).__name__)
                continue
            raise

        if resp.status_code != 429:
            return resp

        retry_after = resp.headers.get("Retry-After")
        try:
            wait = float(retry_after) if retry_after else None
        except (TypeError, ValueError):
            wait = None
        _limiter.note_rate_limited(wait)
        if attempt == 0:
            logger.warning(
                "Scryfall Rate-Limit (429) -- globale Drossel aktiv, ein Wiederholungsversuch."
            )
    if resp is None and last_error is not None:
        raise last_error
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


# Häufige groß geschriebene Wörter, die im Deutschen am Satzanfang oder als
# Substantiv auftauchen, aber nie ein Kartenname sind. Verhindert unnötige
# Scryfall-Abfragen bei jeder Judge-Frage.
_NON_CARD_WORDS = {
    "was", "wie", "wenn", "wer", "wo", "warum", "wieso", "welche", "welcher", "welches",
    "kann", "darf", "muss", "ist", "sind", "hat", "habe", "haben", "wird", "werden",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "eines",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "man", "mein", "meine", "meinem",
    "karte", "karten", "kartentext", "regel", "regeln", "regelfrage", "frage",
    "spieler", "gegner", "zug", "phase", "stapel", "friedhof", "bibliothek", "hand",
    "schlachtfeld", "spiel", "runde", "effekt", "effekte", "fähigkeit", "fähigkeiten",
    "kreatur", "kreaturen", "zauber", "zauberspruch", "instant", "sorcery",
    "und", "oder", "aber", "auch", "noch", "dann", "also", "wenn", "damit", "dass",
    "magic", "gathering", "mtg", "commander", "standard", "modern", "legacy", "pioneer",
}


def extract_card_name_candidates(text: str, max_candidates: int = 4) -> List[str]:
    """
    Extrahiert mögliche Kartennamen aus einer Freitext-Frage (z.B. an den Judge).

    Zweck: Die KI soll ihre Antwort an ECHTEN Kartentexten festmachen statt sie zu
    erfinden. Dafür braucht sie erst Kandidaten, die dann bei Scryfall aufgelöst
    werden. Falsch geratene Kandidaten sind unkritisch -- sie werden bei Scryfall
    schlicht nicht gefunden (und negativ gecacht).

    Erkannt werden:
    - Namen in Anführungszeichen ("Sol Ring", „Sol Ring")
    - Folgen groß geschriebener Wörter (auch mit Verbindern wie "of", "the", "von"
      und mit Komma, z.B. "Krenko, Mob Boss")

    Die Anzahl ist bewusst begrenzt (max_candidates), damit eine einzelne Frage
    nie viele Scryfall-Abfragen auslöst.
    """
    if not text:
        return []

    candidates: List[str] = []

    def _add(raw: str) -> None:
        cleaned = re.sub(r"\s+", " ", raw).strip(" ,.;:!?-")
        if len(cleaned) < 3 or len(cleaned) > 80:
            return
        # Einzelwörter, die offensichtlich keine Kartennamen sind, verwerfen.
        if " " not in cleaned and cleaned.lower() in _NON_CARD_WORDS:
            return
        if cleaned.lower() in {c.lower() for c in candidates}:
            return
        candidates.append(cleaned)

    # 1. Explizit in Anführungszeichen genannte Namen (stärkstes Signal)
    for quoted in re.findall(r'["„»\'`]([^"“«\'`]{3,60})["“«\'`]', text):
        _add(quoted)

    # 2. Folgen groß geschriebener Wörter, inkl. typischer Verbinder
    connector = r"(?:of|the|and|von|der|die|das|und|zu|des)"
    word = r"[A-ZÄÖÜ][\wäöüß'’-]+"
    pattern = rf"\b({word}(?:(?:,?\s+(?:{connector}\s+)?){word})*)"
    for match in re.findall(pattern, text):
        _add(match)
        # Beginnt die Folge mit einem klar generischen Wort ("Effekt Loot der
        # Pfadfinder"), zusätzlich die Variante ohne dieses Wort anbieten --
        # deutsche Sätze hängen solche Wörter oft direkt vor den Kartennamen.
        teile = match.split()
        if len(teile) > 1 and teile[0].lower() in _NON_CARD_WORDS:
            _add(" ".join(teile[1:]))

    return candidates[:max_candidates]


def parse_decklist(deck_liste: str) -> List[Dict[str, Any]]:
    """
    Parst eine Deckliste im Format "1x Sol Ring" oder "1 Sol Ring".

    Ignoriert Kommentare (#, //) und Kategorie-Header (Zeilen die mit : enden).
    Gibt eine Liste von Dicts mit 'count', 'name' und 'sideboard' zurück.

    'sideboard' ist neu: Die Überschrift "Sideboard" wurde zwar übersprungen,
    aber nicht gemerkt -- alle folgenden Karten zählten wie Hauptdeck-Karten.
    Ein 60er-Deck mit 15er-Sideboard erschien dadurch in der Deck-Bibliothek als
    "75 / 60+". Aufrufer, die den Schlüssel nicht auswerten, verhalten sich
    unverändert.
    """
    lines = deck_liste.strip().split('\n')
    parsed = []
    metadata_headers = {"deck", "commander", "companion", "sideboard", "mainboard", "main"}
    im_sideboard = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Kommentare und Kategorie-Header überspringen
        if line.startswith('#') or line.startswith('//') or line.lower().endswith(':'):
            # "// Sideboard" ist die zweite verbreitete Schreibweise.
            if re.match(r'^(?://|#)\s*side\s*board\b', line.lower()):
                im_sideboard = True
            elif re.match(r'^(?://|#)\s*\w+', line.lower()):
                im_sideboard = False
            continue
        if line.lower() in metadata_headers:
            im_sideboard = line.lower() == "sideboard"
            continue
        match = re.match(r'^(\d+)[xX]?\s+(.+)$', line)
        if match:
            parsed.append({
                "count": int(match.group(1)),
                "name": clean_card_name(match.group(2).strip()),
                "sideboard": im_sideboard,
            })
        else:
            parsed.append({"count": 1, "name": clean_card_name(line), "sideboard": im_sideboard})
    return parsed


def best_market_price(preise: List[str]) -> str:
    """Bester (günstigster echter) Marktpreis aus einer Liste von Preis-Strings.

    Ignoriert fehlende/0-Preise. Wird für die 'Best Price'-Anzeige der Kartensuche
    genutzt, damit nicht fälschlich 0.00 € erscheint, nur weil der erste/ausgewählte
    Print (z.B. eine Secret-Lair-Promo) keinen EUR-Preis bei Scryfall hat, während
    andere Editionen derselben Karte reale Preise haben.
    """
    werte = []
    for p in preise or []:
        try:
            v = float(str(p).replace(",", "."))
        except (ValueError, TypeError):
            continue
        if v > 0:
            werte.append(v)
    return f"{min(werte):.2f}" if werte else "0.00"


def _pick_eur(prices: dict) -> str | None:
    """Wählt einen realen EUR-Preis aus einem Scryfall prices-Objekt (eur → eur_foil
    → eur_etched). Gibt None zurück, wenn keiner der Werte gesetzt ist -- so lässt
    sich ein echtes Fehlen von einem tatsächlichen 0-Preis unterscheiden."""
    if not prices:
        return None
    for key in ("eur", "eur_foil", "eur_etched"):
        val = prices.get(key)
        if val:
            return val
    return None


def _extract_card_info(card_data: dict) -> Dict[str, Any]:
    """Extrahiert ein normalisiertes Card-Info-Dict aus einem Scryfall-Datenobjekt."""
    img = card_data.get("image_uris", {}).get("normal", "")
    if not img and "card_faces" in card_data:
        img = card_data["card_faces"][0].get("image_uris", {}).get("normal", "")

    price_val = _pick_eur(card_data.get("prices", {})) or "0.00"

    # Oracle-Text (Regeltext) -- für DFCs/Split-Karten beide Seiten zusammenführen.
    oracle_text = card_data.get("oracle_text", "")
    if not oracle_text and "card_faces" in card_data:
        oracle_text = "\n".join(
            face.get("oracle_text", "") for face in card_data["card_faces"]
        ).strip()

    return {
        "name": card_data["name"],
        "image": img,
        "type": card_data.get("type_line", ""),
        "oracle_text": oracle_text,
        # Manasymbole ("{2}{R}") -- für die Deck-Analyse aussagekräftiger als der
        # reine Manawert, weil daraus die Farbanforderungen hervorgehen.
        "mana_cost": card_data.get("mana_cost", ""),
        "cmc": card_data.get("cmc", 0.0),
        "colors": card_data.get("colors", []),
        "color_identity": card_data.get("color_identity", []),
        # rarity + set werden vom Sammlungs-Filter (Seltenheit / Edition) benötigt.
        # Fehlten sie hier, filterten diese beiden Kriterien immer auf 0 Treffer.
        "rarity": card_data.get("rarity", ""),
        "set": card_data.get("set", ""),
        "set_name": card_data.get("set_name", ""),
        "prices": card_data.get("prices", {}),
        "price": price_val,
        "legalities": card_data.get("legalities", {}),
    }


async def _fetch_cheapest_paper_eur(client: httpx.AsyncClient, card_name: str) -> str | None:
    """Findet den günstigsten realen Papier-EUR-Preis über ALLE Prints einer Karte.

    Notwendig, weil der von Scryfall gelieferte Standard-Print oft keinen EUR-Preis
    hat (z.B. Black Lotus -> Default-Print ist das digitale MTGO-Set 'Vintage Masters'
    mit prices.eur = null, obwohl die Karte real Tausende Euro wert ist). Ohne diesen
    Fallback zeigt die App für solche Karten fälschlich 0.00 €.
    """
    if not card_name:
        return None

    # Ergebnis (auch das negative!) cachen: Karten ohne EUR-Preis am Standard-
    # Print sind häufig (Promos, Spezialdrucke). Ohne dieses Caching löst
    # JEDER Sammlungs-Aufruf für JEDE dieser Karten eine Extra-Suchanfrage aus
    # -- das war der Haupt-Verstärker des Rate-Limit-Sturms.
    cache_key = f"cheapest_eur:{card_name.lower().strip()}"
    cached = scryfall_cache.get(cache_key)
    if cached is not None:
        return cached or None  # "" = bekannt: kein Preis vorhanden

    # Solange Scryfall uns drosselt, ist ein fehlender Preis das kleinere Übel
    # als eine hängende Seite -- der Preis wird beim nächsten Aufruf nachgeholt.
    if _limiter.under_pressure:
        return None

    try:
        # Exakt-Namenssuche über alle Papier-Prints, günstigster EUR zuerst.
        quoted = urllib.parse.quote('!"' + card_name + '" game:paper')
        url = f"https://api.scryfall.com/cards/search?q={quoted}&unique=prints&order=eur&dir=asc"
        resp = await scryfall_request(client, "GET", url)
        if resp.status_code != 200:
            # Bei 429/Fehler NICHT negativ cachen -- sonst würde ein
            # vorübergehendes Limit einen dauerhaft fehlenden Preis festschreiben.
            return None
        prices = []
        for c in resp.json().get("data", []):
            eur = _pick_eur(c.get("prices", {}))
            if eur:
                try:
                    prices.append(float(eur))
                except (ValueError, TypeError):
                    continue
        result = f"{min(prices):.2f}" if prices else ""
        scryfall_cache.set(cache_key, result)
        return result or None
    except Exception:
        logger.debug("cheapest-paper-Preis-Lookup fehlgeschlagen für %s", card_name, exc_info=True)
    return None


async def _build_card_info(client: httpx.AsyncClient, card_data: dict) -> Dict[str, Any]:
    """Wie _extract_card_info, ergänzt aber einen fehlenden Marktpreis über den
    günstigsten Papier-Print (nur wenn der Standard-Print keinen EUR-Preis hat --
    kostet also nur bei diesen Karten einen zusätzlichen Scryfall-Call)."""
    info = _extract_card_info(card_data)
    if _pick_eur(card_data.get("prices", {})) is None:
        cheapest = await _fetch_cheapest_paper_eur(client, card_data.get("name", ""))
        if cheapest:
            info["price"] = cheapest
            info["prices"] = {**info.get("prices", {}), "eur": cheapest}
    return info


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

# Laufende Netzwerk-Auflösungen pro Kartenname ("Single Flight"): Fragen 500
# Nutzer gleichzeitig dieselbe noch nicht gecachte Karte an, geht genau EINE
# Anfrage an Scryfall -- alle anderen warten auf dasselbe Ergebnis.
_inflight: Dict[str, "asyncio.Future"] = {}
_INFLIGHT_TIMEOUT = float(os.getenv("SCRYFALL_INFLIGHT_TIMEOUT", "25"))

# Veraltete Cache-Einträge, die im Hintergrund aufgefrischt werden.
_refresh_queued: Set[str] = set()
MAX_BACKGROUND_REFRESH = int(os.getenv("SCRYFALL_MAX_BACKGROUND_REFRESH", "25"))

# Obergrenze für Einzelabfragen (Fuzzy/Sprachsuche) pro Aufruf. Sie erlauben
# eine BEGRENZTE Degradation: fällt der Sammel-Endpunkt aus (5xx/Timeout),
# bekommen Nutzer wenigstens einen Teil der Daten -- ohne dass daraus wieder
# hunderte Anfragen werden. Bei echter Drosselung (429) greift die Grenze gar
# nicht erst, dort werden Fallbacks komplett übersprungen.
MAX_FALLBACK_LOOKUPS = int(os.getenv("SCRYFALL_MAX_FALLBACK_LOOKUPS", "10"))


def _is_stale(entry: Optional[dict]) -> bool:
    """Eintrag stammt aus einer älteren Version (ohne Regeltext) -- verwendbar,
    aber sollte irgendwann aufgefrischt werden."""
    return bool(entry) and "oracle_text" not in entry


def _schedule_background_refresh(names: List[str]) -> None:
    """
    Frischt veraltete Cache-Einträge NACH der Antwort im Hintergrund auf --
    gedeckelt und dedupliziert.

    Vorher wurden veraltete Einträge verworfen und sofort synchron nachgeladen:
    eine einzige Schema-Änderung entwertete damit den kompletten Cache und löste
    beim nächsten Seitenaufruf hunderte gleichzeitige Anfragen aus. Jetzt wird
    der alte Eintrag ausgeliefert (Seite bleibt schnell) und nur ein kleines
    Kontingent pro Aufruf nachgezogen.
    """
    todo: List[str] = []
    for n in names:
        if len(todo) >= MAX_BACKGROUND_REFRESH:
            break
        key = n.lower().strip()
        if key not in _refresh_queued:
            _refresh_queued.add(key)
            todo.append(n)
    if not todo:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        for n in todo:
            _refresh_queued.discard(n.lower().strip())
        return

    async def _run() -> None:
        try:
            await _fetch_uncached(todo)
        except Exception:
            logger.debug("Hintergrund-Refresh fehlgeschlagen", exc_info=True)
        finally:
            for n in todo:
                _refresh_queued.discard(n.lower().strip())

    loop.create_task(_run())


async def _fetch_uncached(uncached_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Holt Kartendaten für nicht (mehr) gecachte Namen vom Netzwerk.

    Entscheidend für die Stabilität: Ein fehlgeschlagener oder gedrosselter
    Batch löst KEINE Einzel-Fallbacks aus. Früher galten nach einem 429 alle 75
    Karten des Batches als "nicht gefunden", was pro Batch 150 zusätzliche
    Einzelanfragen erzeugte -- Drosselung führte also zu MEHR Last statt zu
    weniger (Rückkopplung). Fallbacks laufen jetzt nur für Namen, die eine
    erfolgreiche Batch-Antwort wirklich nicht kannte.
    """
    scryfall_data: Dict[str, Dict[str, Any]] = {}
    fallback_budget = MAX_FALLBACK_LOOKUPS

    async with scryfall_client() as client:
        for i in range(0, len(uncached_names), 75):
            if _limiter.under_pressure:
                logger.warning(
                    "Scryfall drosselt gerade -- überspringe restliche Batches "
                    "(Daten werden beim nächsten Aufruf nachgeladen)."
                )
                break

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
                        card_info = await _build_card_info(client, c)
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
                elif resp.status_code == 429:
                    # Gedrosselt: NICHT als "nicht gefunden" behandeln und
                    # keine Einzel-Fallbacks starten.
                    logger.warning(
                        "Scryfall-Batch gedrosselt (429) -- %d Karten werden später nachgeladen.",
                        len(chunk),
                    )
                    break
                else:
                    logger.warning(
                        "Scryfall-Batch fehlgeschlagen (HTTP %s) -- begrenzte Einzel-Fallbacks.",
                        resp.status_code,
                    )
            except Exception:
                logger.warning(
                    "Scryfall-Batch nicht erreichbar -- begrenzte Einzel-Fallbacks.",
                    exc_info=True,
                )

            # --- Fallbacks für nicht aufgelöste Namen ---
            # Bei erfolgreichem Batch: nur die vom Batch nicht gekannten Namen.
            # Bei ausgefallenem Batch: dasselbe, aber hart budgetiert, damit ein
            # Ausfall nicht in eine Anfrage-Lawine umschlägt.
            for identifier in chunk:
                if _limiter.under_pressure or fallback_budget <= 0:
                    break

                input_name = identifier["name"]
                input_name_lower = input_name.lower().strip()
                orig_n = name_mapping.get(input_name_lower, input_name)
                orig_n_lower = orig_n.lower().strip()

                if orig_n_lower in scryfall_data:
                    continue  # Bereits gefunden

                fallback_budget -= 1

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


async def build_deck_card_facts(deck_liste: str, max_cards: int = 100) -> tuple:
    """
    Löst eine Deckliste zu BESTÄTIGTEN Kartendaten auf (Scryfall).

    Zweck: Die KI-Deck-Analyse bekam bisher nur die nackte Namensliste und musste
    jeden Kartentext aus dem Gedächtnis rekonstruieren -- bei neuen oder
    lokalisierten Karten hat sie ihn schlicht erfunden. Mit den echten Daten
    begründet das Modell auf Fakten statt auf Erinnerung.

    Args:
        deck_liste: Rohe Deckliste ("4x Lightning Bolt\n1 Sol Ring").
        max_cards: Obergrenze verschiedener Karten (Token- und Kostenschutz).

    Returns:
        (fakten_block, nicht_gefunden)
        fakten_block: mehrzeiliger Text mit Anzahl, Name, Typ, Manakosten und Regeltext
        nicht_gefunden: Namen, die Scryfall nicht auflösen konnte
    """
    eintraege = parse_decklist(deck_liste or "")
    if not eintraege:
        return "", []

    # Mengen je Kartenname zusammenfassen, Reihenfolge der Liste beibehalten.
    mengen: Dict[str, int] = {}
    for eintrag in eintraege:
        name = (eintrag.get("name") or "").strip()
        if name:
            mengen[name] = mengen.get(name, 0) + int(eintrag.get("count") or 1)

    namen = list(mengen.keys())[:max_cards]
    if not namen:
        return "", []

    treffer = await fetch_card_details_cached(namen)

    zeilen: List[str] = []
    nicht_gefunden: List[str] = []
    for name in namen:
        info = treffer.get(name.lower().strip())
        if not info:
            nicht_gefunden.append(name)
            continue
        anzahl = mengen[name]
        kosten = info.get("mana_cost") or ""
        kopf = f"{anzahl}x {info.get('name', name)} — {info.get('type', '')}"
        if kosten:
            kopf += f" — {kosten}"
        kopf += f" — MW {info.get('cmc', 0)}"
        regeltext = (info.get("oracle_text") or "").replace("\n", " ").strip()
        zeilen.append(f"{kopf}\n  Regeltext: {regeltext or '(kein Regeltext)'}")

    return "\n".join(zeilen), nicht_gefunden


def _cache_get_many(keys: List[str]) -> Dict[str, Any]:
    """Holt viele Cache-Keys auf einmal, wenn der Cache das unterstützt.

    Fällt auf Einzelabfragen zurück, damit auch schlanke Cache-Implementierungen
    (z.B. in Tests) weiterhin funktionieren.
    """
    batch_getter = getattr(scryfall_cache, "get_many", None)
    if callable(batch_getter):
        try:
            return batch_getter(keys)
        except Exception:
            logger.warning("Batch-Cache-Lookup fehlgeschlagen, nutze Einzelabfragen", exc_info=True)

    found: Dict[str, Any] = {}
    for key in dict.fromkeys(keys):
        value = scryfall_cache.get(key)
        if value is not None:
            found[key] = value
    return found


async def fetch_card_details_cached(names: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Löst eine Liste von Kartennamen zu Scryfall-Daten auf.

    1. Cache-Lookup (veraltete Einträge werden AUSGELIEFERT und im Hintergrund
       aufgefrischt -- die Antwort wartet nie darauf)
    2. Single-Flight: parallele Anfragen zur selben Karte teilen sich einen Abruf
    3. Batch-Fetch via POST /cards/collection (max 75 pro Batch), global gedrosselt
    4. Fallbacks (Fuzzy / sprachübergreifend) nur für wirklich unbekannte Namen

    Returns:
        Dict[str, CardInfo] – Mapping von name.lower().strip() → Card-Info
    """
    scryfall_data: Dict[str, Dict[str, Any]] = {}
    uncached_names: List[str] = []
    stale_names: List[str] = []

    # --- Phase 1: Cache-Lookup (stale-while-revalidate) ---
    # Alle Keys in EINEM Zugriff holen. Vorher kostete jede einzelne Karte einen
    # eigenen Redis-Roundtrip bzw. eine eigene SQLite-Verbindung -- bei großen
    # Sammlungen war genau das die Hauptursache der langen Ladezeiten.
    lookup_keys: List[str] = []
    for name in names:
        lookup_keys.append(f"card:{name.lower().strip()}")
        if "//" in name:
            lookup_keys.append(f"card:{name.split('//')[0].strip().lower()}")
    cached_map = _cache_get_many(lookup_keys)

    for name in names:
        key = name.lower().strip()
        cached = cached_map.get(f"card:{key}")

        if not cached and "//" in name:
            # DFC: Auch unter dem Vorderseiten-Namen suchen
            front_key = name.split("//")[0].strip().lower()
            cached = cached_map.get(f"card:{front_key}")
            if cached:
                scryfall_data[front_key] = cached

        if cached:
            scryfall_data[key] = cached
            if _is_stale(cached):
                stale_names.append(name)
        else:
            uncached_names.append(name)

    if stale_names:
        _schedule_background_refresh(stale_names)

    if not uncached_names:
        return scryfall_data

    # --- Phase 2: Single-Flight-Aufteilung ---
    loop = asyncio.get_running_loop()
    my_names: List[str] = []
    awaiting: Dict[str, "asyncio.Future"] = {}

    for n in uncached_names:
        key = n.lower().strip()
        existing = _inflight.get(key)
        if existing is not None:
            awaiting[key] = existing
        else:
            _inflight[key] = loop.create_future()
            my_names.append(n)

    # --- Phase 3: Eigene Namen holen, dann Wartende bedienen ---
    if my_names:
        try:
            scryfall_data.update(await _fetch_uncached(my_names))
        finally:
            # Futures IMMER auflösen -- auch im Fehlerfall, damit parallele
            # Anfragen nicht ins Timeout laufen.
            for n in my_names:
                fut = _inflight.pop(n.lower().strip(), None)
                if fut is not None and not fut.done():
                    fut.set_result(scryfall_data.get(n.lower().strip()))

    for key, fut in awaiting.items():
        try:
            info = await asyncio.wait_for(asyncio.shield(fut), timeout=_INFLIGHT_TIMEOUT)
            if info:
                scryfall_data[key] = info
        except Exception:
            logger.debug("Warten auf parallelen Abruf von %s fehlgeschlagen", key)

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
            return await _build_card_info(client, resp.json())
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
                return await _build_card_info(client, search_data["data"][0])
    except Exception:
        pass
    return None
