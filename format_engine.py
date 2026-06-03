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
def parse_deck_liste(deck_liste: str) -> List[Tuple[int, str]]:
    parsed = []
    lines = deck_liste.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue
        
        # Regex to match counts like "1x Sol Ring", "4 Lightning Bolt", "Sol Ring"
        match = re.match(r'^(\d+)\s*x?\s+(.+)$', line)
        if match:
            count = int(match.group(1))
            name = match.group(2).strip()
            parsed.append((count, name))
        else:
            # Fallback if no count is provided (default to 1)
            parsed.append((1, line))
    return parsed

def get_color_identity_symbol_name(symbol: str) -> str:
    # Maps color identity symbols to names
    mapping = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}
    return mapping.get(symbol.upper(), symbol)

# List of MTG basic lands
BASIC_LANDS = {"plains", "island", "swamp", "mountain", "forest", 
               "wastes", "snow-covered plains", "snow-covered island", 
               "snow-covered swamp", "snow-covered mountain", "snow-covered forest"}

class FormatValidator:
    @staticmethod
    async def validate_deck(deck_liste: str, format_name: str, card_details_provider) -> ValidationResult:
        format_name = format_name.lower().strip()
        parsed_cards = parse_deck_liste(deck_liste)
        
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
        
        for count, raw_name in parsed_cards:
            normalized = raw_name.lower().strip()
            # Try to match resolved card info
            info = None
            for k, v in details_dict.items():
                if k == normalized or v.get("name", "").lower().strip() == normalized:
                    info = v
                    break
                    
            if not info:
                unresolved_cards.append(raw_name)
                total_cards += count
                continue
                
            scryfall_name = info["name"]
            norm_scryfall = scryfall_name.lower().strip()
            
            card_counts[norm_scryfall] = card_counts.get(norm_scryfall, 0) + count
            original_names[norm_scryfall] = scryfall_name
            cards_info[norm_scryfall] = info
            total_cards += count

        if unresolved_cards:
            errors.append(f"Folgende Karten wurden in Scryfall nicht gefunden: {', '.join(unresolved_cards)}")

        # Format specific validations
        if format_name == "commander":
            # 1. Total cards must be exactly 100 (including Commander)
            # Wait, standard commander is 100, but players sometimes put 99 + 1 commander or partner commander (98 + 2). We will warn if not 100.
            if total_cards != 100:
                errors.append(f"Ein Commander-Deck muss exakt 100 Karten enthalten. Dein Deck hat {total_cards} Karten.")
                
            # 2. Find commander candidates
            commander_candidates = []
            for norm_name, info in cards_info.items():
                type_line = info.get("type", "").lower()
                # A commander can be a legendary creature, or a planeswalker with commander text, etc.
                if "legendary" in type_line and "creature" in type_line:
                    commander_candidates.append(norm_name)
                    
            if not commander_candidates:
                warnings.append("Keine legendäre Kreatur als Commander im Deck gefunden.")
                commander_identity = set(['W', 'U', 'B', 'R', 'G']) # Fallback: allow all colors
            else:
                # We assume the first legendary creature (or most expensive / user selected) is the commander.
                # In front-end, let's assume the player has a commander.
                # Let's get the color identity of the commander(s)
                # If there are multiple, they might have partner, or one is selected. Let's merge their identities for validation.
                commander_identity = set()
                commander_names = []
                for cand in commander_candidates:
                    info = cards_info[cand]
                    # We only parse the commander if it's explicitly designated or if there's only one.
                    # Since we don't know, let's check all cards color identities against candidate's color identity.
                    # Actually, if we just check color identities, let's check if cards match the color identity of ANY of the candidates.
                    # Or, let's get the first candidate as the primary commander.
                    pass
                
                # To be lenient and accurate: check if there's a commander, and validate that cards fit.
                # Let's find if the user has a line with "commander" in the name or we just use the first candidate.
                primary_commander = commander_candidates[0]
                commander_identity = set(cards_info[primary_commander].get("color_identity", []))
                commander_names.append(original_names[primary_commander])
                
                warnings.append(f"Validiere Farben basierend auf dem angenommenen Commander: {', '.join(commander_names)}")

            # 3. Singleton Rule (Max 1 copy of any non-basic land)
            for norm_name, count in card_counts.items():
                if norm_name not in BASIC_LANDS and count > 1:
                    errors.append(f"Commander ist ein Singleton-Format. Du hast {count}x '{original_names[norm_name]}' im Deck (erlaubt: 1).")

            # 4. Color Identity Rule
            if commander_candidates:
                for norm_name, info in cards_info.items():
                    card_identity = set(info.get("color_identity", []))
                    offending_colors = card_identity - commander_identity
                    if offending_colors:
                        colors_str = ", ".join([get_color_identity_symbol_name(c) for c in offending_colors])
                        errors.append(f"Die Karte '{original_names[norm_name]}' enthält illegale Farben ({colors_str}) für die Farbidentität deines Commanders ({''.join(sorted(list(commander_identity))) or 'Farblos'}).")

        else:
            # 60+ cards deck for Standard, Modern, Legacy, Vintage, Pioneer, Pauper
            if total_cards < 60:
                errors.append(f"Das Deck muss mindestens 60 Karten enthalten. Dein Deck hat {total_cards} Karten.")
                
            # Max 4 copies of any non-basic land
            for norm_name, count in card_counts.items():
                if norm_name not in BASIC_LANDS and count > 4:
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
                "total_cards": total_cards,
                "valid_cards_count": len(cards_info)
            }
        )
