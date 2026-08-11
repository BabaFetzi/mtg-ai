"""
services/multilingual_search.py – Kartensuche in beliebiger Sprache

Problem: Für brandneue Sets gibt es die lokalisierten Kartennamen noch nirgends.
Geprüft am Hobbit-Set (Release 14.08.2026): Scryfall hat KEINE deutschen Drucke,
MTGJSON ebenfalls nicht (360 Karten, 0 Übersetzungen). Eine Nachschlagetabelle
kann es also nicht geben -- die Daten existieren schlicht noch nicht.

Lösung: Es wird gesammelt statt geraten. Nichts, was das Modell vorschlägt,
gilt als Antwort -- entschieden wird nur zwischen ECHT existierenden Karten.

    "Steinstimmen-Goblins"
      1. Sammeln: Modellvorschläge, die es wirklich gibt; dazu eine Wortsuche
         über die Vorschläge UND über die Eingabe selbst
         (name:goblins -> 36 reale Karten, darunter "Stony-Voiced Goblins").
      2. Das Modell wählt aus DIESER Liste -- oder antwortet "KEINE".
         -> "Stony-Voiced Goblins"   <- richtige Karte

Warum ein exakter Vorschlag NICHT genügt: Das Modell schlug für
"Steinstimmen-Goblins" die Karte "Stoneforge Mystic" vor. Die gibt es wirklich
-- und weil sie exakt existierte, wurde sie ungeprüft übernommen. Exaktheit
beweist nur, dass eine Karte EXISTIERT, nicht dass es die gesuchte ist. Auch
ein exakter Vorschlag ist deshalb nur ein Kandidat.

Warum die Fuzzy-Suche nicht bestätigen darf: Sie ist zu grosszügig, matcht auf
Wortanfängen und liefert bereitwillig eine fremde Karte ("Stonespeaker" ->
"Stonespeaker Crystal", "Stone Mystic" -> "Stoneforge Mystic"). Sie gilt nur
noch als Abkürzung, wenn der gelieferte Name dem Vorschlag wirklich ähnelt.

Warum die Auswahl das Modell trifft und kein Zeichenvergleich: Zeichen reichen
nicht. "Duo" und "Pair" sind sich als Zeichenfolge fremd und meinen dasselbe,
während "Stone Mystic" und "Stoneforge Mystic" sich sehr ähnlich sehen und
nichts miteinander zu tun haben. Erfinden kann das Modell dabei nichts: eine
Antwort, die nicht wörtlich in der vorgelegten Liste steht, wird verworfen.

Kosten: Ein günstiger Modellaufruf, und zwar nur, wenn alle anderen Wege
gescheitert sind. Eine bestätigte Zuordnung wird zwischengespeichert, sodass
derselbe Name nie zweimal übersetzt wird. Ein erfolgloser Versuch wird nur
KURZ gemerkt (Standard 15 Minuten): er soll wiederholte Modellaufrufe im
Sekundentakt verhindern, darf aber nicht dazu führen, dass eine Karte für den
Rest des Tages als "nicht auffindbar" gilt -- etwa weil beim ersten Versuch
der API-Schlüssel fehlte oder das Modell kurzzeitig gestört war.
"""

import asyncio
import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

from services.cache import scryfall_cache
from services.scryfall import scryfall_request

logger = logging.getLogger(__name__)

# Abschaltbar, falls die Übersetzungsstufe einmal mehr kosten als nützen sollte.
UEBERSETZUNGSSUCHE_AKTIV = os.getenv("MULTILANG_SEARCH_ENABLED", "true").strip().lower() not in {
    "0", "false", "no", "off"
}

MAX_KANDIDATEN = int(os.getenv("MULTILANG_MAX_CANDIDATES", "5"))

# Wieviele Vorschläge die teureren Stufen (Fuzzy, Wortsuche) durchlaufen.
MAX_FUZZY = 3
MAX_WORTSUCHE = 3
# Ein Suchwort, das auf mehr als so viele Karten passt, ist zu unspezifisch.
MAX_WORTTREFFER = 400
# Soviele echte Namen bekommt das Modell zur Auswahl vorgelegt.
MAX_AUSWAHL = 12
# Ab welcher Ähnlichkeit ein Fuzzy-Treffer als Abkürzung gilt (siehe
# _passt_klar_zusammen). Hoch angesetzt: "Stone Mystic" -> "Stoneforge Mystic"
# erreicht 0.83 und ist trotzdem falsch.
FUZZY_SCHWELLE = 0.88

# Wie lange ein ERFOLGLOSER Versuch gemerkt wird. Bewusst kurz: der Zweck ist
# nur, Modellaufrufe bei Tippen/Neuladen zu bündeln. Wäre er so lang wie die
# normale Cache-Dauer (24 h), würde ein einziger fehlgeschlagener Versuch --
# z.B. während der Server ohne GEMINI_API_KEY lief -- die Karte einen ganzen
# Tag lang unauffindbar machen, ohne dass es irgendwo sichtbar wäre.
NEGATIV_CACHE_SEKUNDEN = int(os.getenv("MULTILANG_NEGATIVE_CACHE_SECONDS", "900"))

# Cache-Version im Schlüssel: erlaubt es, alte Zuordnungen bei einer
# Verbesserung des Verfahrens gezielt ungültig zu machen. v4 = Einträge tragen
# einen Zeitstempel (negative Ergebnisse verfallen eigenständig), und die
# Auswahl läuft über echte Kartennamen -- alte Zuordnungen aus der
# ungeprüften Fuzzy-Bestätigung könnten falsch sein und müssen weg.
_CACHE_PRAEFIX = "namemap:v4:"


def _wirkt_wie_kartenname(begriff: str) -> bool:
    """Grobfilter gegen sinnlose Eingaben, bevor ein Modellaufruf entsteht.

    Ein Kartenname besteht aus Buchstaben und ist entweder mehrteilig oder
    hinreichend lang. Tippfehler wie "xyz" lösen so keinen Aufruf aus.
    """
    text = (begriff or "").strip()
    if len(text) < 4 or len(text) > 80:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]{3}", text):
        return False
    # Mindestens zwei Wörter ODER ein längeres Einzelwort
    return " " in text or "-" in text or len(text) >= 8


def _lies_cache(schluessel: str) -> Tuple[Optional[str], Optional[str]]:
    """Liest einen Cache-Eintrag.

    Returns:
        ("treffer", englischer_name) – bekannte Zuordnung,
        ("fehlschlag", None)        – kürzlich erfolglos, nicht erneut fragen,
        (None, None)                – nichts Gültiges gespeichert.
    """
    eintrag = scryfall_cache.get(schluessel)
    if not isinstance(eintrag, dict):
        # Kein Eintrag – oder ein Eintrag im alten v1-Format (reiner String),
        # der über den neuen Präfix ohnehin nicht mehr gefunden wird.
        return None, None

    name = (eintrag.get("name") or "").strip()
    if name:
        return "treffer", name

    alter = time.time() - float(eintrag.get("zeit") or 0)
    if alter < NEGATIV_CACHE_SEKUNDEN:
        return "fehlschlag", None
    return None, None


def _merke(schluessel: str, name: str) -> None:
    scryfall_cache.set(schluessel, {"name": name, "zeit": time.time()})


async def _frage_modell_nach_englischen_namen(begriff: str) -> List[str]:
    """Lässt das Modell mögliche englische Kartennamen vorschlagen."""
    from services.ai_service import model_lite

    if model_lite is None:
        # Ohne diese Zeile schweigt die Stufe genau dann, wenn man am
        # dringendsten wüsste, warum nichts gefunden wurde.
        logger.warning(
            "Sprachunabhängige Suche übersprungen für %r: kein Sprachmodell verfügbar "
            "(GEMINI_API_KEY gesetzt?)", begriff,
        )
        return []

    prompt = (
        "Du hilfst, einen Magic-the-Gathering-Kartennamen zu identifizieren.\n"
        f"Eingabe (irgendeine gedruckte Sprache, oft Deutsch): \"{begriff}\"\n\n"
        "Nenne die wahrscheinlichsten ENGLISCHEN Kartennamen dazu.\n"
        "- Kennst du den offiziellen englischen Namen, nenne ihn zuerst.\n"
        "- Kennst du ihn nicht (z.B. sehr neue Karte), gib möglichst wörtliche "
        "Übersetzungen an, auch mit alternativen Wortwahlen "
        "(z.B. Duo/Pair, Ruin/Downfall/Doom).\n"
        "- Ist die Eingabe bereits Englisch, gib sie unverändert zurück.\n\n"
        f"Antworte AUSSCHLIESSLICH als JSON: {{\"namen\": [\"...\", \"...\"]}} "
        f"mit höchstens {MAX_KANDIDATEN} Einträgen, ohne Markdown."
    )

    try:
        antwort = await asyncio.to_thread(
            model_lite.generate_content, prompt, None, "kartenname_uebersetzung", None
        )
        roh = (getattr(antwort, "text", "") or "").strip()
    except Exception:
        logger.warning("Namensübersetzung: Modellaufruf fehlgeschlagen", exc_info=True)
        return []

    treffer = re.search(r"\{.*\}", roh, re.DOTALL)
    if not treffer:
        return []
    try:
        namen = json.loads(treffer.group(0)).get("namen", [])
    except (ValueError, AttributeError):
        return []

    sauber = []
    for name in namen:
        if isinstance(name, str) and 2 <= len(name.strip()) <= 80:
            sauber.append(name.strip())
    return sauber[:MAX_KANDIDATEN]


# ----------------------------------------------------------------------
# Namensvergleich
# ----------------------------------------------------------------------
# Wörter, die für die Suche nichts hergeben.
_GENERISCH = {
    "the", "of", "and", "a", "an", "to", "for", "with", "from",
    "der", "die", "das", "und", "von", "des", "dem", "den", "ein", "eine",
}


def _norm(text: str) -> str:
    zerlegt = unicodedata.normalize("NFKD", (text or "").lower())
    ohne_akzente = "".join(z for z in zerlegt if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9 ]+", " ", ohne_akzente)


def _worte(text: str) -> List[str]:
    return [w for w in _norm(text).split() if w]


def _aehnlichkeit(a: str, b: str) -> tuple:
    """(Wort-Ähnlichkeit, Zeichen-Ähnlichkeit) zweier Kartennamen."""
    wa, wb = _worte(a), _worte(b)
    if not wa or not wb:
        return 0.0, 0.0
    beste = [max(SequenceMatcher(None, w, x).ratio() for x in wb) for w in wa]
    wort = sum(beste) / max(len(wa), len(wb))
    zeichen = SequenceMatcher(None, _norm(a).replace(" ", ""), _norm(b).replace(" ", "")).ratio()
    return wort, zeichen


def _passt_klar_zusammen(vorschlag: str, echter_name: str) -> bool:
    """Strenges Tor für die Fuzzy-Bestätigung.

    Scryfalls Fuzzy-Suche ist grosszügig: sie matcht auf Wortanfängen und
    liefert bereitwillig eine völlig andere Karte zurück ("Stonespeaker" ->
    "Stonespeaker Crystal", "Stone Mystic" -> "Stoneforge Mystic"). Genau so
    landete bei der Suche nach "Steinstimmen-Goblins" ein "Stoneforge Mystic"
    im Deck. Ein Fuzzy-Treffer allein ist deshalb KEIN Beweis -- der
    zurückgegebene Name muss dem Vorschlag auch wirklich ähneln.

    Die Schwelle ist bewusst hoch angesetzt. Nachgemessen an echten Fällen
    kostet das nichts: die richtige Karte kommt ohnehin über die Wortsuche in
    die Auswahl (geprüft an Goblin-Duo, Steinstimmen-Goblins, Azogs Untergang,
    Bolgs Gefolge, Der Grosse Ork). Die Fuzzy-Stufe ist damit nur noch eine
    Abkürzung für offensichtliche Treffer -- und kann keine fremde Karte mehr
    einschleusen.
    """
    wort, zeichen = _aehnlichkeit(vorschlag, echter_name)
    return wort >= FUZZY_SCHWELLE and zeichen >= FUZZY_SCHWELLE


async def _hole(client, url: str):
    try:
        return await scryfall_request(client, "GET", url)
    except Exception:
        logger.debug("Scryfall-Abfrage fehlgeschlagen: %s", url, exc_info=True)
        return None


async def _exakter_treffer(client, name: str) -> Optional[dict]:
    """Exakter englischer Name -- unstrittig, keine weitere Prüfung nötig."""
    resp = await _hole(client, "https://api.scryfall.com/cards/named?exact="
                       + urllib.parse.quote(name))
    return resp.json() if resp is not None and resp.status_code == 200 else None


async def _fuzzy_treffer(client, name: str) -> Optional[dict]:
    resp = await _hole(client, "https://api.scryfall.com/cards/named?fuzzy="
                       + urllib.parse.quote(name))
    return resp.json() if resp is not None and resp.status_code == 200 else None


async def _echte_namen_zu(client, kandidat: str) -> List[str]:
    """Sammelt ECHT existierende Kartennamen rund um einen Vorschlag.

    Statt zu hoffen, dass die Fuzzy-Suche den richtigen Namen errät, holen wir
    über die aussagekräftigsten Wörter des Vorschlags eine Liste tatsächlich
    existierender Karten. "Stonevoice Goblins" -> name:goblins -> 36 echte
    Namen, darunter "Stony-Voiced Goblins".
    """
    woerter = [w for w in _worte(kandidat) if len(w) >= 4 and w not in _GENERISCH]
    if not woerter:
        return []
    # Das letzte Wort ist bei Magic-Namen fast immer das Substantiv und
    # übersetzt sich am zuverlässigsten; zusätzlich das längste Wort.
    reihenfolge = []
    for wort in [woerter[-1]] + sorted(woerter, key=len, reverse=True):
        if wort not in reihenfolge:
            reihenfolge.append(wort)

    namen: List[str] = []
    for wort in reihenfolge[:2]:
        resp = await _hole(client, "https://api.scryfall.com/cards/search?q="
                           + urllib.parse.quote(f"name:{wort}") + "&unique=cards")
        if resp is None or resp.status_code != 200:
            continue
        daten = resp.json()
        if daten.get("total_cards", 0) > MAX_WORTTREFFER:
            # Zu unspezifisch -- daraus lässt sich nichts Verlässliches ableiten.
            continue
        for karte in daten.get("data", []):
            name = karte.get("name")
            if name and name not in namen:
                namen.append(name)
    return namen


def _engere_auswahl(kandidaten: List[str], namen: Iterable[str]) -> List[str]:
    """Sortiert echte Namen nach Ähnlichkeit zu den Vorschlägen und kürzt."""
    bewertet = []
    for name in namen:
        bestwert = max((max(_aehnlichkeit(k, name)) for k in kandidaten), default=0.0)
        if bestwert >= 0.45:
            bewertet.append((bestwert, name))
    bewertet.sort(reverse=True)
    return [name for _, name in bewertet[:MAX_AUSWAHL]]


async def _modell_waehlt_aus_echten_namen(begriff: str, auswahl: List[str]) -> Optional[str]:
    """Letzte Entscheidung -- aber NUR zwischen real existierenden Karten.

    Das Modell kann hier nichts mehr erfinden: Antworten, die nicht wörtlich in
    der vorgelegten Liste stehen, werden verworfen. Gleichzeitig darf es sein
    Sprachwissen einsetzen, wo reiner Zeichenvergleich versagt --
    "Duo" und "Pair" sind sich als Zeichenfolge nicht ähnlich, als Bedeutung
    aber identisch.
    """
    from services.ai_service import model_lite

    if model_lite is None or not auswahl:
        return None

    liste = "\n".join(f"- {name}" for name in auswahl)
    prompt = (
        "Eine Magic-the-Gathering-Karte wurde in einer anderen Sprache gesucht.\n"
        f"Gesuchter Name: \"{begriff}\"\n\n"
        "Hier sind ECHTE, existierende englische Kartennamen:\n"
        f"{liste}\n\n"
        "Welcher davon ist dieselbe Karte? Achte auf die Bedeutung, nicht auf "
        "die Schreibweise (z.B. 'Duo' und 'Pair' meinen dasselbe).\n"
        "Antworte mit GENAU einem Namen aus der Liste, unverändert abgeschrieben.\n"
        "Passt keiner wirklich, antworte exakt: KEINE"
    )

    try:
        antwort = await asyncio.to_thread(
            model_lite.generate_content, prompt, None, "kartenname_auswahl", None
        )
        roh = (getattr(antwort, "text", "") or "").strip()
    except Exception:
        logger.warning("Namensauswahl: Modellaufruf fehlgeschlagen", exc_info=True)
        return None

    if not roh or roh.upper().startswith("KEINE"):
        return None
    # Nur eine Antwort zählt, die WÖRTLICH in der Liste steht.
    for name in auswahl:
        if _norm(roh) == _norm(name):
            return name
    logger.info("Namensauswahl verworfen: %r steht nicht in der Auswahl", roh[:80])
    return None


async def finde_karte_sprachunabhaengig(client, begriff: str) -> Optional[dict]:
    """
    Letzte Suchstufe: Kartenname in beliebiger Sprache -> bestätigte Karte.

    Args:
        client: offener httpx-AsyncClient (Scryfall).
        begriff: Eingabe des Nutzers in beliebiger Sprache.

    Returns:
        Das vollständige Scryfall-Kartenobjekt, oder None wenn nichts bestätigt
        werden konnte. Es wird NIEMALS ein unbestätigter Vorschlag geliefert --
        auch dann nicht, wenn er zufällig eine echt existierende Karte trifft.
    """
    if not UEBERSETZUNGSSUCHE_AKTIV or not _wirkt_wie_kartenname(begriff):
        return None

    schluessel = _CACHE_PRAEFIX + begriff.lower().strip()
    art, gemerkt = _lies_cache(schluessel)
    if art == "treffer":
        logger.info("Sprachunabhängige Suche: %r -> %r (aus Cache)", begriff, gemerkt)
        return await _exakter_treffer(client, gemerkt)
    if art == "fehlschlag":
        logger.info(
            "Sprachunabhängige Suche übersprungen für %r: vor weniger als %d s bereits "
            "erfolglos versucht", begriff, NEGATIV_CACHE_SEKUNDEN,
        )
        return None

    kandidaten = await _frage_modell_nach_englischen_namen(begriff)
    if not kandidaten:
        # Kein Modell / keine verwertbare Antwort: NICHT als Fehlschlag merken,
        # sonst zementiert ein technischer Ausfall das Ergebnis.
        return None

    # --- Stufe 1: Menge ECHT existierender Kartennamen aufbauen -----------
    # Hier wird nichts entschieden, nur gesammelt. Alles Folgende sind reale
    # Karten -- aber KEINE davon gilt schon als richtig.
    echte: dict = {}
    for nummer, kandidat in enumerate(kandidaten):
        karte = await _exakter_treffer(client, kandidat)
        if karte:
            echte[karte["name"]] = karte
            continue
        if nummer < MAX_FUZZY:
            karte = await _fuzzy_treffer(client, kandidat)
            if karte and _passt_klar_zusammen(kandidat, karte.get("name", "")):
                echte[karte["name"]] = karte

    # Auch die Wörter der EINGABE selbst durchsuchen. Kreaturentypen und
    # Eigennamen sind über Sprachen hinweg oft fast gleich ("Steinstimmen-
    # Goblins" enthält "Goblins", "Azogs Untergang" enthält "Azog"). Das
    # findet die richtige Karte unabhängig davon, was das Modell vorschlägt.
    for quelle in [begriff] + kandidaten[:MAX_WORTSUCHE]:
        for name in await _echte_namen_zu(client, quelle):
            echte.setdefault(name, None)

    auswahl = _engere_auswahl([begriff] + kandidaten, echte.keys())
    if not auswahl:
        logger.info(
            "Sprachunabhängige Suche: für %r existiert zu den Vorschlägen %s keine "
            "passende echte Karte", begriff, kandidaten,
        )
        _merke(schluessel, "")
        return None

    # --- Stufe 2: das Modell wählt -- aber nur aus echten Namen -----------
    # Reiner Zeichenvergleich kann hier nicht entscheiden: "Duo" und "Pair"
    # sind sich als Zeichenfolge unähnlich, meinen aber dasselbe -- während
    # "Stone Mystic" und "Stoneforge Mystic" sich sehr ähnlich sehen und doch
    # nichts miteinander zu tun haben.
    wahl = await _modell_waehlt_aus_echten_namen(begriff, auswahl)
    if not wahl:
        logger.info(
            "Sprachunabhängige Suche: %r -- keiner der %d echten Namen passte",
            begriff, len(auswahl),
        )
        _merke(schluessel, "")
        return None

    karte = echte.get(wahl) or await _exakter_treffer(client, wahl)
    if karte is None:
        return None
    logger.info(
        "Sprachunabhängige Suche: %r -> %r (aus %d echten Namen gewählt)",
        begriff, karte.get("name"), len(auswahl),
    )
    _merke(schluessel, karte.get("name", ""))
    return karte
