"""
services/rules_corpus.py – Offizielle Comprehensive Rules als Wissensquelle

Warum: Der Judge kannte bisher keinerlei Regeltext. Das Regelbuch der App sind
14 fest einprogrammierte Regeln im Frontend, auf die die KI keinen Zugriff hat.
Regelfragen wurden also allein aus dem Modellgedächtnis beantwortet.

Dies ist der eine Fall, in dem sich echtes Nachschlagen lohnt: Die
Comprehensive Rules sind unstrukturierte Prosa (im Gegensatz zu Kartendaten,
die Scryfall bereits exakt abfragbar macht).

Bewusst LEXIKALISCHE Suche statt Vektor-Embeddings:
- Regeltexte sind extrem begriffslastig ("deathtouch", "state-based action"),
  da trifft eine Begriffssuche zuverlässig.
- Keine zusätzliche Abhängigkeit, kein Modell, keine Indexpflege.

Der Regeltext wird NICHT im Repository mitgeliefert (Urheberrecht liegt bei
Wizards of the Coast), sondern beim ersten Gebrauch heruntergeladen und lokal
zwischengespeichert. Schlägt das fehl, arbeitet der Judge wie bisher weiter --
nur ohne Regelzitate.
"""

import logging
import math
import os
import re
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Von Wizards veröffentlichte Textfassung. Erscheint eine neue Edition, kann die
# Adresse per Umgebungsvariable aktualisiert werden -- oder es wird über
# MTG_RULES_FILE eine lokal abgelegte Datei verwendet.
RULES_URL = os.getenv(
    "MTG_RULES_URL",
    "https://media.wizards.com/2024/downloads/MagicCompRules%2020240206.txt",
)
RULES_FILE = os.getenv("MTG_RULES_FILE", "")
RULES_CACHE_PATH = os.getenv("MTG_RULES_CACHE_PATH", "mtg_comprehensive_rules.txt")
RULES_ENABLED = os.getenv("MTG_RULES_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

# Eine Regelzeile beginnt mit ihrer Nummer: "104.2a Ein Spieler gewinnt ..."
_RULE_LINE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s+(\S.*)$")

# Direkte Regelnummer in der Frage ("Was sagt Regel 704.5f?")
_RULE_REF = re.compile(r"\b(\d{3}\.\d+[a-z]?)\b")

_WORD = re.compile(r"[a-zäöüß0-9]{3,}", re.IGNORECASE)

# Sehr häufige Wörter, die für die Trefferbewertung nichts beitragen.
_STOPWORDS = {
    # Englisch
    "the", "and", "that", "this", "with", "for", "are", "its", "his", "her", "their",
    "has", "have", "can", "may", "not", "one", "any", "all", "from", "each", "then",
    "rule", "rules", "player", "players", "card", "cards", "game", "see", "also",
    # Deutsch
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "und", "oder", "aber", "wenn", "wie", "was", "wer", "wird", "werden", "ist",
    "sind", "kann", "darf", "muss", "man", "ich", "sich", "nicht", "auch", "noch",
    "funktioniert", "passiert", "bedeutet", "frage", "magic", "gathering",
}

# Brücke Deutsch -> Englisch: Die Regeln liegen nur auf Englisch vor, die Fragen
# der Nutzer sind deutsch. Ausschliesslich offizielle deutsche MTG-Begriffe.
_DE_EN: Dict[str, Tuple[str, ...]] = {
    "fliegend": ("flying",),
    "flugfähigkeit": ("flying",),
    "todesberührung": ("deathtouch",),
    "lebensverknüpfung": ("lifelink",),
    "trampelschaden": ("trample",),
    "erstschlag": ("first", "strike"),
    "doppelschlag": ("double", "strike"),
    "wachsamkeit": ("vigilance",),
    "eile": ("haste",),
    "verteidiger": ("defender",),
    "fluchsicher": ("hexproof",),
    "schutz": ("protection",),
    "unzerstörbar": ("indestructible",),
    "bedrohlich": ("menace",),
    "reichweite": ("reach",),
    "schleier": ("shroud",),
    "blitz": ("flash",),
    "verursacht": ("deals",),
    "schaden": ("damage",),
    "stapel": ("stack",),
    "priorität": ("priority",),
    "friedhof": ("graveyard",),
    "bibliothek": ("library",),
    "schlachtfeld": ("battlefield",),
    "exil": ("exile",),
    "kreatur": ("creature",),
    "kreaturen": ("creature",),
    "zauberspruch": ("spell",),
    "zaubersprüche": ("spell",),
    "spontanzauber": ("instant",),
    "hexerei": ("sorcery",),
    "verzauberung": ("enchantment",),
    "artefakt": ("artifact",),
    "planeswalker": ("planeswalker",),
    "angreifer": ("attacking", "creature"),
    "angreifen": ("attacking",),
    "blocker": ("blocking", "creature"),
    "blocken": ("blocking",),
    "kampf": ("combat",),
    "kampfphase": ("combat", "phase"),
    "segment": ("step",),
    "phase": ("phase",),
    "tappen": ("tap",),
    "enttappen": ("untap",),
    "opfern": ("sacrifice",),
    "zerstören": ("destroy",),
    "ziehen": ("draw",),
    "ziel": ("target",),
    "ziele": ("target",),
    "fähigkeit": ("ability",),
    "fähigkeiten": ("ability",),
    "ausgelöste": ("triggered",),
    "auslöser": ("triggered", "ability"),
    "aktivierte": ("activated",),
    "manakosten": ("mana", "cost"),
    "manawert": ("mana", "value"),
    "kopie": ("copy",),
    "marke": ("counter",),
    "marken": ("counter",),
    "widerstandskraft": ("toughness",),
    "stärke": ("power",),
    "zustandsbasierte": ("state", "based", "actions"),
    "verrechnung": ("resolve",),
    "verrechnet": ("resolves",),
    "gegenzauber": ("counter", "spell"),
    "wiederbelebung": ("return", "graveyard"),
    "legendär": ("legendary",),
    "mulligan": ("mulligan",),
    "oberbefehlshaber": ("commander",),
    "kommandeur": ("commander",),
}


# BM25-Parameter (Standardwerte): k1 dämpft häufige Wiederholungen, b steuert
# die Längennormalisierung.
_BM25_K1 = 1.5
_BM25_B = 0.75


class _Korpus:
    """Geparste Regeln plus invertierter Index mit BM25-Bewertung.

    BM25 statt reiner Begriffszählung, weil sonst jede der zehn Regeln, die
    "deathtouch" erwähnen, gleich stark wiegt. BM25 bevorzugt die Regel, in der
    die gesuchten Begriffe dicht beieinander stehen -- also die eigentliche
    Definition statt einer beiläufigen Erwähnung.
    """

    def __init__(self, regeln: List[Tuple[str, str]]):
        self.regeln = regeln
        self.nach_nummer = {nummer: text for nummer, text in regeln}
        self._postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self._laengen: List[int] = []

        for i, (_, text) in enumerate(regeln):
            tokens = _tokenize(text)
            self._laengen.append(len(tokens))
            haeufigkeit: Dict[str, int] = defaultdict(int)
            for term in tokens:
                haeufigkeit[term] += 1
            for term, tf in haeufigkeit.items():
                self._postings[term].append((i, tf))

        self._anzahl = len(regeln) or 1
        self._avg_len = (sum(self._laengen) / self._anzahl) if self._laengen else 1.0

    def suche(self, terme: Sequence[str], limit: int) -> List[Tuple[str, str]]:
        punkte: Dict[int, float] = defaultdict(float)
        for term in set(terme):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = math.log(1 + (self._anzahl - len(postings) + 0.5) / (len(postings) + 0.5))
            for i, tf in postings:
                laenge = self._laengen[i] or 1
                nenner = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * laenge / self._avg_len)
                punkte[i] += idf * (tf * (_BM25_K1 + 1)) / nenner
        beste = sorted(punkte.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [self.regeln[i] for i, _ in beste]


def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def _erweitere_begriffe(frage: str, extra_terms: Optional[Sequence[str]] = None) -> List[str]:
    """Baut die Suchbegriffe: Wörter der Frage, deutsche Begriffe ins Englische
    übersetzt, plus optionale Zusatzbegriffe (z.B. aus echten Kartentexten)."""
    terme: List[str] = []
    for wort in _tokenize(frage):
        if wort in _STOPWORDS:
            continue
        terme.append(wort)
        terme.extend(_DE_EN.get(wort, ()))
    for wort in _tokenize(" ".join(extra_terms or [])):
        if wort not in _STOPWORDS:
            terme.append(wort)
    return terme


def parse_rules(text: str) -> List[Tuple[str, str]]:
    """Zerlegt die Comprehensive Rules in (Regelnummer, Regeltext).

    Reine Funktion ohne Netzwerk -- damit testbar.
    """
    regeln: List[Tuple[str, str]] = []
    gesehen = set()
    for zeile in (text or "").splitlines():
        zeile = zeile.strip()
        treffer = _RULE_LINE.match(zeile)
        if not treffer:
            continue
        nummer, inhalt = treffer.group(1), treffer.group(2).strip()
        # Das Inhaltsverzeichnis listet dieselben Nummern ohne Fliesstext.
        if nummer in gesehen or len(inhalt) < 25:
            continue
        gesehen.add(nummer)
        regeln.append((nummer, inhalt))
    return regeln


_korpus: Optional[_Korpus] = None
_load_lock = threading.Lock()
_load_versucht = False


def _lade_rohtext() -> Optional[str]:
    """Liest die Regeln aus einer lokalen Datei, dem Cache oder lädt sie herunter."""
    for pfad in (RULES_FILE, RULES_CACHE_PATH):
        if pfad and os.path.exists(pfad):
            try:
                with open(pfad, "r", encoding="utf-8-sig", errors="replace") as f:
                    return f.read()
            except Exception:
                logger.warning("Regeldatei %s nicht lesbar", pfad, exc_info=True)

    try:
        import httpx
        resp = httpx.get(RULES_URL, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning("Comprehensive Rules nicht abrufbar (HTTP %s)", resp.status_code)
            return None
        text = resp.content.decode("utf-8-sig", errors="replace")
        try:
            with open(RULES_CACHE_PATH, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            logger.warning("Regeln konnten nicht zwischengespeichert werden", exc_info=True)
        return text
    except Exception:
        logger.warning("Herunterladen der Comprehensive Rules fehlgeschlagen", exc_info=True)
        return None


def _hole_korpus() -> Optional[_Korpus]:
    """Lädt den Korpus einmalig. Scheitert das, wird es nicht erneut versucht."""
    global _korpus, _load_versucht
    if _korpus is not None or _load_versucht:
        return _korpus
    with _load_lock:
        if _korpus is not None or _load_versucht:
            return _korpus
        _load_versucht = True
        rohtext = _lade_rohtext()
        if not rohtext:
            return None
        regeln = parse_rules(rohtext)
        if not regeln:
            logger.warning("Regeltext enthielt keine erkennbaren Regeln")
            return None
        _korpus = _Korpus(regeln)
        logger.info("Comprehensive Rules geladen: %d Regeln.", len(regeln))
    return _korpus


def suche_regeln(
    frage: str,
    extra_terms: Optional[Sequence[str]] = None,
    limit: int = 4,
) -> List[Tuple[str, str]]:
    """
    Findet die zur Frage passendsten offiziellen Regeln.

    Args:
        frage: Freitextfrage (deutsch oder englisch).
        extra_terms: Zusatzbegriffe, z.B. der englische Regeltext genannter
            Karten -- schlägt die Brücke von der deutschen Frage zu den
            englischen Regeln.
        limit: Höchstzahl zurückgegebener Regeln.

    Returns:
        Liste von (Regelnummer, Regeltext); leer, wenn keine Regeln verfügbar sind.
    """
    if not RULES_ENABLED or not frage:
        return []
    korpus = _hole_korpus()
    if korpus is None:
        return []

    # Direkt genannte Regelnummern haben Vorrang.
    ergebnis: List[Tuple[str, str]] = []
    for nummer in _RULE_REF.findall(frage):
        text = korpus.nach_nummer.get(nummer)
        if text and all(nummer != n for n, _ in ergebnis):
            ergebnis.append((nummer, text))

    if len(ergebnis) < limit:
        for eintrag in korpus.suche(_erweitere_begriffe(frage, extra_terms), limit):
            if all(eintrag[0] != n for n, _ in ergebnis):
                ergebnis.append(eintrag)
            if len(ergebnis) >= limit:
                break
    return ergebnis[:limit]


def _reset_for_tests() -> None:
    """Setzt den geladenen Korpus zurück (nur für Tests)."""
    global _korpus, _load_versucht
    _korpus = None
    _load_versucht = False
