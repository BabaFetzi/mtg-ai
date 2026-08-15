"""tests/test_pauper.py -- Pauper misst an der Legalität, nicht am Standarddruck.

Pauper erlaubt jede Karte, die irgendwann einmal als Common gedruckt wurde.
Die Seltenheit in den Kartendaten ist immer die des neuesten Standarddrucks --
Lightning Bolt ist dort längst uncommon und trotzdem seit jeher Pauper-legal.
Die Prüfung meldete genau diese Seltenheit und behauptete damit über eine
legale Karte, sie sei verboten.
"""

import pytest

from format_engine import FormatValidator


def karte(name, typ="Creature — Human", rarity="common", pauper="legal"):
    info = {
        "name": name,
        "type": typ,
        "oracle_text": "",
        "color_identity": [],
        "rarity": rarity,
        "legalities": {},
    }
    if pauper is not None:
        info["legalities"]["pauper"] = pauper
    return info


def _provider(karten):
    async def f(namen):
        return {k["name"].lower(): k for k in karten}
    return f


BERG = karte("Mountain", typ="Basic Land — Mountain")


def _deck(name, anzahl=4, laender=56):
    """4 Kopien plus Standardland -- die Kopiengrenze ist hier nicht das Thema."""
    return f"{anzahl} {name}\n{laender} Mountain"


@pytest.mark.asyncio
async def test_uncommon_nachdruck_einer_pauper_karte_ist_legal():
    """Der eigentliche Fehler: der neueste Druck ist uncommon, die Karte aber
    legal. Vorher stand im Ergebnis, Pauper erlaube nur Commons."""
    bolt = karte("Lightning Bolt", rarity="uncommon", pauper="legal")
    ergebnis = await FormatValidator.validate_deck(
        _deck("Lightning Bolt"), "pauper", _provider([bolt, BERG]))

    assert ergebnis.legal is True
    assert not any("Seltenheit" in w for w in ergebnis.warnings), ergebnis.warnings
    assert not any("Common" in w for w in ergebnis.warnings), ergebnis.warnings


@pytest.mark.asyncio
async def test_nicht_pauper_legale_karte_wird_beanstandet():
    force = karte("Force of Will", rarity="rare", pauper="not_legal")
    ergebnis = await FormatValidator.validate_deck(
        _deck("Force of Will"), "pauper", _provider([force, BERG]))

    assert ergebnis.legal is False
    assert any("nicht legal" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_gebannte_karte_bleibt_gebannt():
    sinkhole = karte("Sinkhole", rarity="common", pauper="banned")
    ergebnis = await FormatValidator.validate_deck(
        _deck("Sinkhole"), "pauper", _provider([sinkhole, BERG]))

    assert ergebnis.legal is False
    assert any("gebannt" in f for f in ergebnis.errors), ergebnis.errors


@pytest.mark.asyncio
async def test_ohne_legalitaetsdaten_wird_ehrlich_gewarnt():
    """Fehlen die Daten, darf die Prüfung nichts behaupten -- weder legal noch
    verboten. Sie sagt, dass sie es nicht weiss."""
    unbekannt = karte("Testkarte ohne Daten", rarity="rare", pauper=None)
    ergebnis = await FormatValidator.validate_deck(
        _deck("Testkarte ohne Daten"), "pauper", _provider([unbekannt, BERG]))

    assert ergebnis.legal is True
    assert any("keine Legalitätsdaten" in w for w in ergebnis.warnings), ergebnis.warnings
    # Keine Behauptung über die Seltenheit des Standarddrucks.
    assert not any("Seltenheit ist" in w for w in ergebnis.warnings), ergebnis.warnings


@pytest.mark.asyncio
async def test_pauper_deck_braucht_60_karten():
    bolt = karte("Lightning Bolt", rarity="uncommon", pauper="legal")
    ergebnis = await FormatValidator.validate_deck(
        _deck("Lightning Bolt", 4, 20), "pauper", _provider([bolt, BERG]))

    assert ergebnis.legal is False
    assert any("60 Karten" in f for f in ergebnis.errors), ergebnis.errors
