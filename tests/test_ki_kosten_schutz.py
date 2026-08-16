"""Was verhindert, dass die KI auf fremde Rechnung läuft.

Die sprachunabhängige Kartensuche war der einzige Weg, über den ein NICHT
angemeldeter Besucher Gemini-Aufrufe auslösen konnte: bis zu zwei je Suche,
ungezählt, ungedrosselt, an einem Endpunkt ohne Anmeldung. Wer tausend
erfundene Kartennamen durchprobiert, hat damit direkt das Google-Guthaben des
Betreibers verbrannt.

Dazu zwei kleinere, aber teure Punkte: welches Modell tatsächlich abgerechnet
wurde (der angefragte Alias sagt es nicht), und dass ein gescheiterter Aufruf
dem Kunden nicht sein Kontingent wegnimmt.
"""

from unittest.mock import AsyncMock, patch

import pytest

import services.multilingual_search as ms
from services.ai_service import _tatsaechliches_modell


# ----------------------------------------------------------------------
# Die Lücke selbst
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ohne_anmeldung_kein_modellaufruf():
    """Der Kern. Ohne Benutzernamen darf die Stufe das Modell nicht anfassen."""
    with patch.object(ms, "_frage_modell_nach_englischen_namen",
                      new=AsyncMock(return_value=["Lightning Bolt"])) as modell:
        treffer = await ms.finde_karte_sprachunabhaengig(None, "Blitzschlag Karte", "")

    assert treffer is None
    modell.assert_not_called()


@pytest.mark.asyncio
async def test_mit_anmeldung_wird_gezaehlt():
    """Angemeldet darf die Stufe laufen -- aber sie muss auf das Kontingent
    gebucht werden, sonst ist sie wieder unbegrenzt."""
    with patch.object(ms, "_frage_modell_nach_englischen_namen",
                      new=AsyncMock(return_value=[])) as modell, \
         patch("services.usage_limiter.check_and_increment_search_ai",
               new=AsyncMock(return_value=True)) as zaehler:
        await ms.finde_karte_sprachunabhaengig(None, "Blitzschlag Karte", "anna")

    zaehler.assert_awaited_once_with("anna")
    modell.assert_awaited_once()


@pytest.mark.asyncio
async def test_bei_erschoepftem_kontingent_kein_modellaufruf():
    with patch.object(ms, "_frage_modell_nach_englischen_namen",
                      new=AsyncMock(return_value=["Lightning Bolt"])) as modell, \
         patch("services.usage_limiter.check_and_increment_search_ai",
               new=AsyncMock(return_value=False)):
        treffer = await ms.finde_karte_sprachunabhaengig(None, "Blitzschlag Karte", "anna")

    assert treffer is None
    modell.assert_not_called()


@pytest.mark.asyncio
async def test_unsinnige_eingaben_kosten_gar_nichts():
    """Der Grobfilter greift VOR dem Zähler -- sonst verbrauchte ein Tippfehler
    Kontingent."""
    with patch("services.usage_limiter.check_and_increment_search_ai",
               new=AsyncMock(return_value=True)) as zaehler:
        for unsinn in ("xy", "", "a b", "!!!", "x" * 200):
            assert await ms.finde_karte_sprachunabhaengig(None, unsinn, "anna") is None

    zaehler.assert_not_awaited()


# ----------------------------------------------------------------------
# Welches Modell hat tatsächlich abgerechnet?
# ----------------------------------------------------------------------
def test_die_konkrete_modellfassung_wird_festgehalten():
    """Angefragt wird ein Alias ("gemini-flash-latest"), weil feste Versionen
    für neue Schlüssel wegbrechen können. Google zeigt den Alias aber laufend
    auf neuere Modelle um -- in der Abrechnung standen 2.5 Flash, 3.5 Flash
    Lite, 3.6 Flash und 3.7 Flash nebeneinander. Wer nur den Alias
    protokolliert, kann die Kosten keinem Modell zuordnen.
    """
    class Antwort:
        model_version = "gemini-3.7-flash"

    assert _tatsaechliches_modell(Antwort(), "gemini-flash-latest") == "gemini-3.7-flash"


def test_ohne_angabe_bleibt_der_angefragte_name_stehen():
    """Liefert das SDK nichts, ist der Alias die einzige verfügbare Wahrheit --
    einen Modellnamen zu erfinden wäre schlechter."""
    class Antwort:
        pass

    assert _tatsaechliches_modell(Antwort(), "gemini-flash-latest") == "gemini-flash-latest"
    assert _tatsaechliches_modell(None, "gemini-flash-lite-latest") == "gemini-flash-lite-latest"
