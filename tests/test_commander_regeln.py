"""tests/test_commander_regeln.py – Commander-Eignung, Partner, Hintergrund, Companion

Was einem Commander-Spieler beim Benutzen sofort aufgefallen wäre:

1. Jede legendäre Kreatur ODER jeder Planeswalker galt als Commander.
   Planeswalker dürfen es aber nur, wenn ihr Regeltext das ausdrücklich sagt --
   illegale Decks wurden dadurch als legal ausgewiesen.
2. Zwei Commander (Partner, Friends forever, Hintergrund) waren gar nicht
   vorgesehen. Diese Mechaniken sind sehr verbreitet und verändern die
   Farbidentität des ganzen Decks -- ohne sie war die Farbprüfung wertlos.
3. Ein Companion steht ausserhalb des Decks. Er wurde mitgezählt und liess ein
   korrektes 100-Karten-Deck als "101 Karten" durchfallen.
"""

import pytest

from format_engine import (
    FormatValidator,
    darf_commander_sein,
    paar_erlaubt,
    parse_deck_bereiche,
    partner_art,
)

# --- Bausteine für Testkarten -----------------------------------------
def karte(name, typ, text="", farben=()):
    return {"name": name, "type": typ, "oracle_text": text,
            "color_identity": list(farben), "legalities": {}, "rarity": "rare"}


KRENKO = karte("Krenko, Mob Boss", "Legendary Creature — Goblin Warrior", farben=["R"])
# Ein gewöhnlicher Planeswalker -- KEIN Commander.
CHANDRA = karte("Chandra, Torch of Defiance", "Legendary Planeswalker — Chandra", farben=["R"])
# Ein Planeswalker, der es ausdrücklich erlaubt.
TEFERI = karte("Teferi, Temporal Archmage",
               "Legendary Planeswalker — Teferi",
               "Teferi, Temporal Archmage can be your commander.", farben=["U"])
THRASIOS = karte("Thrasios, Triton Hero", "Legendary Creature — Merfolk Wizard",
                 "Partner (You can have two commanders if both have partner.)", farben=["G", "U"])
VIAL_SMASHER = karte("Vial Smasher the Fierce", "Legendary Creature — Goblin Berserker",
                     "Partner (You can have two commanders if both have partner.)", farben=["B", "R"])
WILSON = karte("Wilson, Refined Grizzly", "Legendary Creature — Bear Warrior",
               "Choose a Background (You can have a Background as a second commander.)", farben=["G"])
HINTERGRUND = karte("Criminal Past", "Legendary Enchantment — Background",
                    "Commander creatures you own have skulk.", farben=["B"])


def _provider(karten):
    async def f(namen):
        return {k["name"].lower(): k for k in karten}
    return f


# ----------------------------------------------------------------------
# Wer darf überhaupt Commander sein?
# ----------------------------------------------------------------------
def test_legendaere_kreatur_darf():
    assert darf_commander_sein(KRENKO) is True


def test_gewoehnlicher_planeswalker_darf_nicht():
    """Der eigentliche Fehler: Chandra galt als Commander."""
    assert darf_commander_sein(CHANDRA) is False


def test_planeswalker_mit_ausdruecklicher_erlaubnis_darf():
    assert darf_commander_sein(TEFERI) is True


def test_nichtlegendaere_kreatur_darf_nicht():
    assert darf_commander_sein(karte("Grizzly Bears", "Creature — Bear")) is False


@pytest.mark.asyncio
async def test_markierter_planeswalker_wird_beanstandet():
    deck = "Commander\n1 Chandra, Torch of Defiance\nDeck\n99 Mountain"
    berg = karte("Mountain", "Basic Land — Mountain")
    ergebnis = await FormatValidator.validate_deck(deck, "commander", _provider([CHANDRA, berg]))

    assert ergebnis.legal is False
    assert any("kann aber keiner sein" in f for f in ergebnis.errors), ergebnis.errors


# ----------------------------------------------------------------------
# Zwei Commander
# ----------------------------------------------------------------------
def test_partner_wird_erkannt():
    assert partner_art(THRASIOS) == "partner"
    assert partner_art(HINTERGRUND) == "background"
    assert partner_art(WILSON) == "waehlt_background"
    assert partner_art(KRENKO) is None


def test_zwei_partner_sind_erlaubt():
    assert paar_erlaubt(THRASIOS, VIAL_SMASHER) is True


def test_kreatur_plus_hintergrund_ist_erlaubt():
    assert paar_erlaubt(WILSON, HINTERGRUND) is True


def test_zwei_beliebige_legenden_sind_nicht_erlaubt():
    assert paar_erlaubt(KRENKO, THRASIOS) is False


@pytest.mark.asyncio
async def test_partner_paar_vereint_die_farbidentitaet():
    """Der praktische Nutzen: Thrasios (GU) + Vial Smasher (BR) erlauben
    zusammen vier Farben. Ohne Partner-Unterstützung hätte die Prüfung entweder
    gemeckert oder alle Farben durchgewinkt."""
    deck = ("Commander\n1 Thrasios, Triton Hero\n1 Vial Smasher the Fierce\n"
            "Deck\n98 Mountain")
    berg = karte("Mountain", "Basic Land — Mountain")
    ergebnis = await FormatValidator.validate_deck(
        deck, "commander", _provider([THRASIOS, VIAL_SMASHER, berg]))

    assert ergebnis.details["total_cards"] == 100
    assert not any("dürfen nicht gemeinsam" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_unerlaubtes_paar_wird_beanstandet():
    deck = "Commander\n1 Krenko, Mob Boss\n1 Thrasios, Triton Hero\nDeck\n98 Mountain"
    berg = karte("Mountain", "Basic Land — Mountain")
    ergebnis = await FormatValidator.validate_deck(
        deck, "commander", _provider([KRENKO, THRASIOS, berg]))

    assert ergebnis.legal is False
    assert any("nicht gemeinsam" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_drei_commander_werden_beanstandet():
    deck = ("Commander\n1 Krenko, Mob Boss\n1 Thrasios, Triton Hero\n"
            "1 Vial Smasher the Fierce\nDeck\n97 Mountain")
    berg = karte("Mountain", "Basic Land — Mountain")
    ergebnis = await FormatValidator.validate_deck(
        deck, "commander", _provider([KRENKO, THRASIOS, VIAL_SMASHER, berg]))

    assert any("höchstens zwei" in f for f in ergebnis.errors), ergebnis.errors


# ----------------------------------------------------------------------
# Companion
# ----------------------------------------------------------------------
def test_companion_zaehlt_nicht_zum_deck():
    """Ein Companion steht ausserhalb des Decks. Vorher machte er aus einem
    korrekten 100-Karten-Deck ein 101-Karten-Deck."""
    deck = "Commander\n1 Krenko, Mob Boss\nDeck\n99 Mountain\nCompanion\n1 Lurrus of the Dream-Den"
    haupt = sum(a for a, _, _, sb in parse_deck_bereiche(deck) if not sb)
    assert haupt == 100


@pytest.mark.asyncio
async def test_deck_mit_companion_bleibt_legal():
    deck = "Commander\n1 Krenko, Mob Boss\nDeck\n99 Mountain\nCompanion\n1 Lurrus of the Dream-Den"
    berg = karte("Mountain", "Basic Land — Mountain")
    lurrus = karte("Lurrus of the Dream-Den", "Legendary Creature — Cat Nightmare", farben=["W", "B"])
    ergebnis = await FormatValidator.validate_deck(
        deck, "commander", _provider([KRENKO, berg, lurrus]))

    assert ergebnis.details["total_cards"] == 100
    assert not any("exakt 100 Karten" in f for f in ergebnis.errors), ergebnis.errors
