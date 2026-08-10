"""
tests/test_rulebook_numbers.py – Regelnummern des Regelbuchs gegen das Original prüfen

Anlass: Die 14 kuratierten deutschen Grundregeln im Frontend trugen zu SIEBEN
Regeln eine falsche Nummer. Das Regelbuch behauptete z.B. "702.8 Todesberührung",
offiziell ist 702.8 aber "Flash"; Todesberührung ist 702.2.

Warum das zählt: Magic-Spieler zitieren Regelnummern gegenüber Schiedsrichtern.
Eine falsche Nummer ist schlimmer als gar keine. Seit das Regelbuch daneben die
echten Comprehensive Rules anzeigt, widersprach sich die App zudem selbst.

Dieser Test liest die Nummern direkt aus der Frontend-Komponente und prüft sie
gegen den offiziellen Regeltext. Er wird übersprungen, wenn der Regeltext lokal
nicht vorliegt (er wird nicht mitgeliefert, sondern bei Bedarf geladen).
"""

import pathlib
import re

import pytest

import services.rules_corpus as rc

KOMPONENTE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "mtg-frontend" / "src" / "components" / "entdecken" / "RegelbuchAnsicht.jsx"
)

# Erwartetes Stichwort im offiziellen Regeltext je kuratierter Regel.
ERWARTETES_STICHWORT = {
    "101.1": "card takes precedence",
    "117.1": "priority",
    "117.3c": "priority",
    "400.7": "new object",
    "506.1": "combat phase has five steps",
    "508.1": "declares attackers",
    "509.1": "declares blockers",
    "608.2b": "targets are still legal",
    "702.2": "deathtouch",
    "702.4": "double strike",
    "702.19": "trample",
    "702.11": "hexproof",
    "702.12": "indestructible",
    "704.5f": "toughness 0 or less",
}


def _kuratierte_regeln():
    """Liest (Nummer, Titel) aus der Frontend-Komponente."""
    quelltext = KOMPONENTE.read_text(encoding="utf-8")
    return re.findall(r'\{\s*id:\s*"([^"]+)",\s*title:\s*"([^"]+)"', quelltext)


@pytest.fixture(scope="module")
def korpus():
    rc._reset_for_tests()
    k = rc._hole_korpus()
    if k is None:
        pytest.skip("Offizieller Regeltext lokal nicht verfügbar")
    return k


def test_komponente_ist_lesbar():
    regeln = _kuratierte_regeln()
    assert len(regeln) >= 14, f"Nur {len(regeln)} kuratierte Regeln gefunden"


def test_jede_kuratierte_nummer_ist_abgedeckt():
    """Neue kuratierte Regeln müssen hier mit aufgenommen werden."""
    nummern = {nr for nr, _ in _kuratierte_regeln()}
    assert nummern <= set(ERWARTETES_STICHWORT), (
        "Unbekannte Regelnummer(n) im Regelbuch -- bitte im Test ergänzen und "
        f"gegen die offiziellen Regeln prüfen: {nummern - set(ERWARTETES_STICHWORT)}"
    )


@pytest.mark.parametrize("nummer,titel", _kuratierte_regeln())
def test_regelnummer_passt_zum_offiziellen_thema(nummer, titel, korpus):
    """Die Nummer muss offiziell existieren UND dasselbe Thema behandeln."""
    stichwort = ERWARTETES_STICHWORT.get(nummer)
    if stichwort is None:
        pytest.fail(f"Regel {nummer} ({titel}) ist im Test nicht hinterlegt")

    # Text der Regel selbst oder -- bei Sammelnummern wie 702.2 -- ihrer Unterregeln.
    texte = [t for nr, t in korpus.regeln if nr == nummer or nr.startswith(nummer)]
    assert texte, f"Regel {nummer} ({titel}) existiert offiziell nicht"

    zusammen = " ".join(texte).lower()
    assert stichwort.lower() in zusammen, (
        f"Regel {nummer} wird im Regelbuch als '{titel}' geführt, behandelt "
        f"offiziell aber etwas anderes: {texte[0][:100]}"
    )
