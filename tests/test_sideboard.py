"""tests/test_sideboard.py – Sideboard sauber vom Hauptdeck trennen

Die Überschrift "Sideboard" wurde zwar erkannt, aber nicht gemerkt: alle
folgenden Karten landeten im selben Topf wie das Hauptdeck. Folgen:

- Ein reguläres 60er-Deck mit 15er-Sideboard wurde als 75-Karten-Deck geprüft.
- In Commander (exakt 100 Karten) meldete die Prüfung dadurch fälschlich einen
  Fehler, obwohl das Deck korrekt war.
- Das Sideboard selbst blieb ungeprüft -- die 15-Karten-Grenze existierte nicht.

Für einen Turnierspieler ist das der Unterschied zwischen einem Werkzeug, dem
er vor dem Turnier vertraut, und einem, das er lieber zweimal nachrechnet.
"""

import pytest

from format_engine import FormatValidator, parse_deck_bereiche


def _hauptdeck(deck: str) -> int:
    return sum(a for a, _, _, sb in parse_deck_bereiche(deck) if not sb)


def _sideboard(deck: str) -> int:
    return sum(a for a, _, _, sb in parse_deck_bereiche(deck) if sb)


# ----------------------------------------------------------------------
# Zerlegung
# ----------------------------------------------------------------------
def test_arena_export_trennt_haupt_und_sideboard():
    deck = "Deck\n4 Lightning Bolt\n56 Mountain\n\nSideboard\n3 Abrade\n2 Smash to Smithereens"
    assert _hauptdeck(deck) == 60
    assert _sideboard(deck) == 5


def test_kommentar_schreibweise_wird_auch_erkannt():
    """Viele Deckseiten exportieren "// Sideboard" statt einer blossen Überschrift."""
    deck = "4 Lightning Bolt\n56 Mountain\n// Sideboard\n3 Abrade"
    assert _hauptdeck(deck) == 60
    assert _sideboard(deck) == 3


def test_side_board_mit_leerzeichen():
    deck = "60 Mountain\n// Side Board\n2 Abrade"
    assert _sideboard(deck) == 2


def test_ohne_sideboard_bleibt_alles_hauptdeck():
    deck = "4 Lightning Bolt\n56 Mountain"
    assert _hauptdeck(deck) == 60
    assert _sideboard(deck) == 0


def test_abschnitt_nach_sideboard_zaehlt_wieder_zum_hauptdeck():
    """Nach einem erneuten "Deck"-Kopf endet der Sideboard-Abschnitt."""
    deck = "Deck\n30 Mountain\nSideboard\n2 Abrade\nDeck\n30 Island"
    assert _hauptdeck(deck) == 60
    assert _sideboard(deck) == 2


def test_commander_markierung_schlaegt_sideboard():
    """Eine ausdrücklich als Commander markierte Karte gehört nie ins Sideboard."""
    deck = "Sideboard\n1 Krenko, Mob Boss *CMDR*"
    eintraege = parse_deck_bereiche(deck)
    assert eintraege[0][2] is True   # ist_commander
    assert eintraege[0][3] is False  # ist_sideboard


# ----------------------------------------------------------------------
# Prüfung gegen die Formatregeln
# ----------------------------------------------------------------------
def _karten(namen_und_typ):
    async def provider(namen):
        return {
            n.lower(): {"name": n, "type": typ, "color_identity": [], "legalities": {}, "rarity": "common"}
            for n, typ in namen_und_typ.items()
        }
    return provider


@pytest.mark.asyncio
async def test_sechzig_plus_sideboard_ist_legal():
    """Der gemeldete Fehler: 60 + 15 wurde als 75-Karten-Deck geprüft."""
    deck = "Deck\n60 Mountain\n\nSideboard\n" + "\n".join(f"1 Abrade{i}" for i in range(15))
    karten = {"Mountain": "Basic Land"}
    karten.update({f"Abrade{i}": "Instant" for i in range(15)})

    ergebnis = await FormatValidator.validate_deck(deck, "modern", _karten(karten))

    assert ergebnis.details["total_cards"] == 60
    assert ergebnis.details["sideboard_cards"] == 15
    assert ergebnis.legal is True, ergebnis.errors


@pytest.mark.asyncio
async def test_zu_grosses_sideboard_wird_beanstandet():
    deck = "Deck\n60 Mountain\n\nSideboard\n" + "\n".join(f"1 Abrade{i}" for i in range(16))
    karten = {"Mountain": "Basic Land"}
    karten.update({f"Abrade{i}": "Instant" for i in range(16)})

    ergebnis = await FormatValidator.validate_deck(deck, "modern", _karten(karten))

    assert ergebnis.legal is False
    assert any("Sideboard darf höchstens 15" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_hauptdeck_unter_sechzig_faellt_trotz_sideboard_auf():
    """Ein 50er-Deck mit 15er-Sideboard sah vorher wie 65 Karten aus und ging
    fälschlich durch."""
    deck = "Deck\n50 Mountain\n\nSideboard\n" + "\n".join(f"1 Abrade{i}" for i in range(15))
    karten = {"Mountain": "Basic Land"}
    karten.update({f"Abrade{i}": "Instant" for i in range(15)})

    ergebnis = await FormatValidator.validate_deck(deck, "modern", _karten(karten))

    assert ergebnis.legal is False
    assert any("mindestens 60 Karten" in f for f in ergebnis.errors), ergebnis.errors
    assert ergebnis.details["total_cards"] == 50


@pytest.mark.asyncio
async def test_kopiengrenze_gilt_ueber_beide_bereiche():
    """Turnierregel: höchstens 4 Kopien über Haupt- UND Sideboard zusammen.
    3 im Hauptdeck plus 2 im Sideboard sind also 5 und damit zu viel."""
    deck = "Deck\n3 Lightning Bolt\n57 Mountain\n\nSideboard\n2 Lightning Bolt"
    karten = {"Mountain": "Basic Land", "Lightning Bolt": "Instant"}

    ergebnis = await FormatValidator.validate_deck(deck, "modern", _karten(karten))

    assert ergebnis.legal is False
    assert any("maximal 4 Kopien" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_commander_mit_sideboard_bleibt_bei_hundert():
    """Vorher schlug die 100-Karten-Prüfung fehl, sobald ein Sideboard dabei war."""
    deck = "Commander\n1 Krenko, Mob Boss\nDeck\n99 Mountain\n\nSideboard\n2 Abrade"
    karten = {"Mountain": "Basic Land", "Krenko, Mob Boss": "Legendary Creature — Goblin Warrior", "Abrade": "Instant"}

    ergebnis = await FormatValidator.validate_deck(deck, "commander", _karten(karten))

    assert ergebnis.details["total_cards"] == 100
    assert not any("exakt 100 Karten" in f for f in ergebnis.errors), ergebnis.errors
    # Hinweis statt Fehler: Commander kennt kein Sideboard.
    assert any("kein Sideboard" in w for w in ergebnis.warnings), ergebnis.warnings


# ----------------------------------------------------------------------
# Die zweite Fundstelle: der Parser für Deck-Bibliothek und Simulator
# ----------------------------------------------------------------------
def test_scryfall_parser_kennzeichnet_sideboard():
    """services/scryfall.py hat einen EIGENEN Parser -- er ignorierte die
    Sideboard-Grenze ebenfalls. Dadurch zeigte die Deck-Bibliothek "75 / 60+"
    für ein korrektes 60er-Deck mit 15er-Sideboard."""
    from services.scryfall import parse_decklist

    parsed = parse_decklist("Deck\n60 Mountain\nSideboard\n3 Abrade")
    haupt = sum(p["count"] for p in parsed if not p["sideboard"])
    side = sum(p["count"] for p in parsed if p["sideboard"])

    assert haupt == 60
    assert side == 3


def test_scryfall_parser_kommentar_schreibweise():
    from services.scryfall import parse_decklist

    parsed = parse_decklist("60 Mountain\n// Sideboard\n2 Abrade")
    assert sum(p["count"] for p in parsed if p["sideboard"]) == 2


def test_scryfall_parser_ohne_sideboard_unveraendert():
    """Aufrufer, die den neuen Schlüssel nicht auswerten, dürfen sich nicht
    anders verhalten als vorher."""
    from services.scryfall import parse_decklist

    parsed = parse_decklist("4 Lightning Bolt\n56 Mountain")
    assert [(p["count"], p["name"]) for p in parsed] == [(4, "Lightning Bolt"), (56, "Mountain")]
    assert all(p["sideboard"] is False for p in parsed)
