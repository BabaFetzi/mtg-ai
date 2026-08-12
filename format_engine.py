import re
from typing import List, Dict, Set, Tuple, Optional
from pydantic import BaseModel
from banned_lists import fetch_banned_cards, fetch_restricted_cards

class ValidationResult(BaseModel):
    legal: bool
    errors: List[str]
    warnings: List[str]
    details: Dict

# Simple helper to clean and parse deck lines
def parse_deck_bereiche(deck_liste: str) -> List[Tuple[int, str, bool, bool]]:
    """Zerlegt eine Deckliste in (anzahl, name, ist_commander, ist_sideboard).

    Die Überschrift "Sideboard" wurde bisher zwar erkannt, aber nicht gemerkt:
    alle folgenden Karten landeten im selben Topf wie das Hauptdeck. Ein
    reguläres 60er-Deck mit 15er-Sideboard wurde dadurch als 75-Karten-Deck
    geprüft, und in Commander (exakt 100 Karten) meldete die Prüfung fälschlich
    einen Fehler. Zugleich blieb das Sideboard ungeprüft -- die 15-Karten-Grenze
    existierte nicht.
    """
    parsed = []
    lines = deck_liste.strip().split('\n')
    current_section_is_commander = False
    current_section_is_sideboard = False

    metadata_headers = {"deck", "commander", "companion", "sideboard", "mainboard", "main"}
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line is a section header
        if line.lower() in metadata_headers:
            current_section_is_commander = line.lower() == "commander"
            current_section_is_sideboard = line.lower() == "sideboard"
            continue

        if line.startswith('#') or line.startswith('//'):
            lower_line = line.lower()
            # "// Sideboard" ist die zweite verbreitete Schreibweise neben der
            # blossen Überschrift (Arena exportiert ohne, viele Seiten mit).
            if re.match(r'^(?://|#)\s*side\s*board\b', lower_line):
                current_section_is_sideboard = True
                current_section_is_commander = False
                continue
            if "commander" in lower_line or "cmdr" in lower_line:
                header_match = re.match(r'^(?://|#)\s*(commander|cmdr)s?\b', lower_line)
                if header_match:
                    current_section_is_commander = True
                    current_section_is_sideboard = False
                    continue
            header_reset = re.match(r'^(?://|#)\s*(?!commander|cmdr)\w+', lower_line)
            if header_reset:
                current_section_is_commander = False
                current_section_is_sideboard = False
                continue
            
            # If it's a generic comment, check if it contains commander keyword inline, else skip
            if not any(keyword in lower_line for keyword in ["commander", "cmdr"]):
                continue

        # Parse quantity and card name
        match = re.match(r'^(\d+)\s*x?\s+(.+)$', line)
        if match:
            count = int(match.group(1))
            name = match.group(2).strip()
        else:
            count = 1
            name = line
            
        # Detect inline commander tag
        is_cmdr = current_section_is_commander
        cmdr_tag_pattern = r'\s+(?:\*CMDR\*|\*CMDR\b|\[CMDR\]|\(CMDR\)|\/\/ Commander)\s*$'
        if re.search(cmdr_tag_pattern, name, re.IGNORECASE):
            is_cmdr = True
            name = re.sub(cmdr_tag_pattern, '', name, flags=re.IGNORECASE).strip()
            
        # Eine ausdrücklich als Commander markierte Karte gehört nie ins Sideboard.
        parsed.append((count, name, is_cmdr, current_section_is_sideboard and not is_cmdr))

    return parsed


def parse_deck_liste_with_commander(deck_liste: str) -> List[Tuple[int, str, bool]]:
    """Unveränderte Signatur für bestehende Aufrufer: alle Karten ohne
    Unterscheidung nach Bereich."""
    return [(anzahl, name, cmdr) for anzahl, name, cmdr, _ in parse_deck_bereiche(deck_liste)]


def parse_deck_liste(deck_liste: str) -> List[Tuple[int, str]]:
    return [(count, name) for count, name, _ in parse_deck_liste_with_commander(deck_liste)]

def get_color_identity_symbol_name(symbol: str) -> str:
    # Maps color identity symbols to names
    mapping = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}
    return mapping.get(symbol.upper(), symbol)

# List of MTG basic lands
BASIC_LANDS = {"plains", "island", "swamp", "mountain", "forest", 
               "wastes", "snow-covered plains", "snow-covered island", 
               "snow-covered swamp", "snow-covered mountain", "snow-covered forest"}

# List of cards that allow unlimited copies
UNLIMITED_COPY_CARDS = {
    "relentless rats",
    "rat colony",
    "dragon's approach",
    "shadowborn apostle",
    "persistent petitioners",
    "templar knight"
}

class FormatValidator:
    @staticmethod
    async def validate_deck(deck_liste: str, format_name: str, card_details_provider) -> ValidationResult:
        format_name = format_name.lower().strip()
        bereiche = parse_deck_bereiche(deck_liste)
        parsed_cards_with_cmdr = [(a, n, c) for a, n, c, _ in bereiche]
        parsed_cards = [(count, name) for count, name, _ in parsed_cards_with_cmdr]

        # Sideboard-Karten zählen NICHT zum Hauptdeck. Die Kopiengrenze gilt
        # dagegen über beide Bereiche zusammen -- so sagen es die Turnierregeln.
        sideboard_karten = sum(a for a, _, _, sb in bereiche if sb)
        hat_sideboard_abschnitt = any(sb for _, _, _, sb in bereiche)

        if not parsed_cards:
            return ValidationResult(
                legal=False,
                errors=["Das Deck ist leer."],
                warnings=[],
                details={"format": format_name, "total_cards": 0}
            )

        card_names = [name for _, name in parsed_cards]
        # Fetch card details from Scryfall cache/API provider
        details_dict = await card_details_provider(card_names)
        
        errors = []
        warnings = []
        total_cards = 0
        
        # Card counts map (normalized name to count)
        card_counts: Dict[str, int] = {}
        # Original name map (normalized name to actual Scryfall name)
        original_names: Dict[str, str] = {}
        # Scryfall card details map
        cards_info: Dict[str, dict] = {}
        
        unresolved_cards = []
        
        # Über bereiche laufen statt über parsed_cards: nur so ist bekannt, welche
        # Karte im Sideboard steht. total_cards zählt AUSSCHLIESSLICH das
        # Hauptdeck -- card_counts dagegen beide Bereiche, weil die
        # Kopiengrenze über Haupt- und Sideboard zusammen gilt.
        for count, raw_name, _ist_cmdr, ist_sideboard in bereiche:
            normalized = raw_name.lower().strip()
            # Try to match resolved card info
            info = None
            for k, v in details_dict.items():
                if k == normalized or v.get("name", "").lower().strip() == normalized:
                    info = v
                    break

            if not info:
                unresolved_cards.append(raw_name)
                if not ist_sideboard:
                    total_cards += count
                continue

            scryfall_name = info["name"]
            norm_scryfall = scryfall_name.lower().strip()

            card_counts[norm_scryfall] = card_counts.get(norm_scryfall, 0) + count
            original_names[norm_scryfall] = scryfall_name
            cards_info[norm_scryfall] = info
            if not ist_sideboard:
                total_cards += count

        if unresolved_cards:
            errors.append(f"Folgende Karten wurden in Scryfall nicht gefunden: {', '.join(unresolved_cards)}")

        # Resolve explicit commander names to normalized scryfall name
        resolved_explicit_commanders = set()
        for count, raw_name, is_cmdr in parsed_cards_with_cmdr:
            if is_cmdr:
                normalized = raw_name.lower().strip()
                # Find in details_dict
                for k, v in details_dict.items():
                    if k == normalized or v.get("name", "").lower().strip() == normalized:
                        resolved_explicit_commanders.add(v["name"].lower().strip())

        # Format specific validations
        if format_name == "commander":
            # 1. Total cards must be exactly 100 (including Commander)
            if total_cards != 100:
                errors.append(f"Ein Commander-Deck muss exakt 100 Karten enthalten. Dein Deck hat {total_cards} Karten.")
                
            # 2. Find commander candidates
            commander_candidates = []
            
            # Check if we have explicit commanders
            tagged_commanders = []
            for norm_name in cards_info:
                if norm_name in resolved_explicit_commanders:
                    tagged_commanders.append(norm_name)
            
            if tagged_commanders:
                commander_candidates = tagged_commanders
                commander_names = [original_names[c] for c in tagged_commanders]
                commander_identity = set()
                for c in tagged_commanders:
                    commander_identity.update(cards_info[c].get("color_identity", []))
                warnings.append(f"Validiere Farben basierend auf dem explizit markierten Commander: {', '.join(commander_names)}")
            else:
                # Fallback to legendaries
                legendaries = []
                for norm_name, info in cards_info.items():
                    type_line = info.get("type", "").lower()
                    if "legendary" in type_line and ("creature" in type_line or "planeswalker" in type_line):
                        legendaries.append(norm_name)
                
                if len(legendaries) == 1:
                    primary = legendaries[0]
                    commander_identity = set(cards_info[primary].get("color_identity", []))
                    commander_names = [original_names[primary]]
                    warnings.append(f"Validiere Farben basierend auf der einzigen legendären Kreatur/Planeswalker im Deck: {commander_names[0]}")
                    commander_candidates = [primary]
                elif len(legendaries) > 1:
                    warnings.append("Mehrere legendäre Kreaturen im Deck gefunden. Bitte markiere deinen Commander mit *CMDR* (z.B. '1 Krenko, Mob Boss *CMDR*') für eine präzise Farbprüfung.")
                    commander_identity = set(['W', 'U', 'B', 'R', 'G']) # Allow all colors to avoid false positives
                    commander_candidates = legendaries
                    commander_names = ["Keiner (Mehrere Kandidaten)"]
                else:
                    warnings.append("Keine legendäre Kreatur/Planeswalker als Commander im Deck gefunden. Bitte markiere deinen Commander mit *CMDR*.")
                    commander_identity = set(['W', 'U', 'B', 'R', 'G']) # Allow all colors
                    commander_names = []

            # 3. Singleton Rule (Max 1 copy of any non-basic land)
            for norm_name, count in card_counts.items():
                if norm_name not in BASIC_LANDS and norm_name not in UNLIMITED_COPY_CARDS and count > 1:
                    errors.append(f"Commander ist ein Singleton-Format. Du hast {count}x '{original_names[norm_name]}' im Deck (erlaubt: 1).")

            # 4. Color Identity Rule
            if commander_candidates:
                for norm_name, info in cards_info.items():
                    card_identity = set(info.get("color_identity", []))
                    offending_colors = card_identity - commander_identity
                    if offending_colors:
                        colors_str = ", ".join([get_color_identity_symbol_name(c) for c in offending_colors])
                        errors.append(f"Die Karte '{original_names[norm_name]}' enthält illegale Farben ({colors_str}) für die Farbidentität deines Commanders ({''.join(sorted(list(commander_identity))) or 'Farblos'}).")

            # 5. Commander kennt kein Sideboard (ausser dem Companion, der als
            #    eigener Abschnitt exportiert wird und hier nicht als Sideboard
            #    gilt). Ein Sideboard-Abschnitt deutet auf eine falsch
            #    zusammengesetzte Liste hin -- als Warnung, nicht als Fehler,
            #    weil manche Runden hausintern damit spielen.
            if sideboard_karten:
                warnings.append(
                    f"Commander kennt kein Sideboard. Die {sideboard_karten} Karten "
                    "im Sideboard-Abschnitt wurden nicht zu den 100 Karten gezählt."
                )

        else:
            # 60+ cards deck for Standard, Modern, Legacy, Vintage, Pioneer, Pauper
            if total_cards < 60:
                errors.append(f"Das Deck muss mindestens 60 Karten enthalten. Dein Deck hat {total_cards} Karten.")

            # Sideboard: höchstens 15 Karten in allen Turnierformaten.
            if sideboard_karten > 15:
                errors.append(
                    f"Das Sideboard darf höchstens 15 Karten enthalten. Deines hat {sideboard_karten}."
                )
                
            # Max 4 copies of any non-basic land
            for norm_name, count in card_counts.items():
                if norm_name not in BASIC_LANDS and norm_name not in UNLIMITED_COPY_CARDS and count > 4:
                    errors.append(f"In diesem Format sind maximal 4 Kopien einer Karte erlaubt. Du hast {count}x '{original_names[norm_name]}'.")

        # 5. Format Legality check (Scryfall legality)
        banned_in_format = await fetch_banned_cards(format_name)
        restricted_in_format = await fetch_restricted_cards(format_name)
        
        for norm_name, info in cards_info.items():
            scryfall_name = original_names[norm_name]
            legalities = info.get("legalities", {})
            status = legalities.get(format_name, "unknown")
            
            # Direct check or cached check
            if status == "banned" or scryfall_name.lower().strip() in banned_in_format:
                errors.append(f"Die Karte '{scryfall_name}' ist in {format_name.capitalize()} gebannt.")
            elif status == "restricted" or scryfall_name.lower().strip() in restricted_in_format:
                # Vintage restricted cards can only have 1 copy
                count = card_counts.get(norm_name, 0)
                if count > 1:
                    errors.append(f"Die Karte '{scryfall_name}' ist in {format_name.capitalize()} limitiert (restricted). Max 1 Kopie erlaubt. Du hast {count}x.")
            elif status == "not_legal":
                errors.append(f"Die Karte '{scryfall_name}' ist in {format_name.capitalize()} nicht legal.")
            
            # Pauper only allows commons
            if format_name == "pauper":
                rarity = info.get("rarity", "").lower()
                # Sometimes a card is common in some set but Scryfall returns its default print rarity. 
                # Scryfall has a "pauper" legality which we already checked via `legalities.get("pauper")`, so that's the primary check.
                if status == "unknown" and "common" not in rarity:
                    warnings.append(f"Karte '{scryfall_name}' Seltenheit ist '{rarity}'. Pauper erlaubt nur Commons.")

        legal = len(errors) == 0
        return ValidationResult(
            legal=legal,
            errors=errors,
            warnings=warnings,
            details={
                "format": format_name,
                # Hauptdeck ohne Sideboard -- das ist die Zahl, gegen die die
                # 60er- bzw. 100er-Regel geprüft wird.
                "total_cards": total_cards,
                "sideboard_cards": sideboard_karten,
                "has_sideboard": hat_sideboard_abschnitt,
                "valid_cards_count": len(cards_info)
            }
        )
