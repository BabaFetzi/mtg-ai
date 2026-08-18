"""services/kartennamen_gedaechtnis.py -- was einmal geprüft wurde, bleibt bekannt.

Das Problem
-----------
Die sprachunabhängige Suche kostet bis zu zwei Gemini-Aufrufe. Ihr Ergebnis --
"Steinstimmen-Goblins" ist "Stony-Voiced Goblins" -- lag bisher im Kartencache,
und der verfällt nach 24 Stunden. Danach wurde dieselbe Übersetzung erneut
gekauft. Jeden Tag, für jeden Namen, für einen Zusammenhang, der sich nie
ändert.

Warum man das gefahrlos dauerhaft behalten darf
-----------------------------------------------
Hier landet ausschliesslich, was gegen Scryfall BESTÄTIGT wurde. Die Suche
übernimmt keinen Modellvorschlag: sie sammelt echt existierende Karten und
lässt das Modell nur zwischen diesen wählen (siehe den Kopf von
services/multilingual_search.py). Gespeichert wird also ein nachgeschlagener
Fakt, keine Modellmeinung.

Das ist der Unterschied, auf den es ankommt. Ein Ergebnis, das man gegen eine
Wahrheitsquelle prüfen kann, darf man behalten. Eine Deck-Analyse kann man
nicht prüfen -- deshalb wird die hier auch nicht gespeichert, und ein
"Gedächtnis" für ähnliche Decks wird es bewusst nie geben.

Gemeinsam für alle
------------------
Die Tabelle kennt keinen Benutzernamen. Wer einen Namen einmal auflöst,
erspart ihn allen anderen für immer -- bei mehreren tausend Nutzern ist das
der eigentliche Effekt, nicht die Ersparnis beim Einzelnen.

Ausfallverhalten
----------------
Jede Funktion hier fängt Datenbankfehler ab und tut so, als wüsste sie nichts.
Eine klemmende Datenbank darf die Suche nicht lahmlegen -- sie fällt dann auf
den bisherigen Weg zurück (Cache, danach KI) und ist nur langsamer und teurer,
nicht kaputt.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Woher eine Zuordnung stammt.
QUELLE_KI = "ki_bestaetigt"       # Modell hat vorgeschlagen, Scryfall bestätigt
QUELLE_SCRYFALL = "scryfall"      # ohne Modell gefunden (lokalisierter Druck)

MAX_LAENGE = 255


def _schluessel(begriff: str) -> str:
    return (begriff or "").strip().lower()[:MAX_LAENGE]


async def nachschlagen(begriff: str) -> Optional[str]:
    """Der bestätigte englische Kartenname, oder None.

    Zählt bei einem Treffer mit, wie oft das Gedächtnis eine KI-Anfrage
    erspart hat.
    """
    schluessel = _schluessel(begriff)
    if not schluessel:
        return None

    try:
        from database import get_db_session

        async with get_db_session() as session:
            treffer = (await session.execute(
                text("SELECT karten_name FROM kartenname_gedaechtnis "
                     "WHERE begriff = :b"),
                {"b": schluessel})).scalar()
            if not treffer:
                return None

            # Nur mitzählen, nicht darauf verlassen: schlägt das UPDATE fehl,
            # ist der Treffer trotzdem gültig.
            try:
                await session.execute(
                    text("UPDATE kartenname_gedaechtnis SET treffer = treffer + 1 "
                         "WHERE begriff = :b"), {"b": schluessel})
            except Exception:
                logger.debug("Trefferzähler nicht erhöht", exc_info=True)

            return treffer
    except Exception:
        logger.debug("Kartennamen-Gedächtnis nicht lesbar", exc_info=True)
        return None


async def merken(begriff: str, karten_name: str,
                 quelle: str = QUELLE_KI) -> bool:
    """Speichert eine BESTÄTIGTE Zuordnung dauerhaft.

    Args:
        begriff: Was der Nutzer eingegeben hat.
        karten_name: Der englische Name, wie Scryfall ihn führt. Muss aus
            einer Scryfall-Antwort stammen -- ein Modellvorschlag hat hier
            nichts verloren.
        quelle: Womit bestätigt wurde.

    Returns:
        Ob gespeichert wurde. False heisst nur "nicht gemerkt", nie "Fehler
        für den Nutzer".
    """
    schluessel = _schluessel(begriff)
    name = (karten_name or "").strip()[:MAX_LAENGE]

    # Ein leerer Name wäre ein Fehlschlag, und Fehlschläge gehören NICHT ins
    # dauerhafte Gedächtnis: dass eine Karte heute nicht gefunden wird, heisst
    # nicht, dass es sie morgen nicht gibt. Neue Sets erscheinen laufend, und
    # Scryfall trägt lokalisierte Drucke Wochen später nach. Dafür gibt es den
    # kurzen Negativ-Cache in multilingual_search.
    if not schluessel or not name:
        return False

    # Sich selbst zu merken bringt nichts: wenn Eingabe und Kartenname gleich
    # sind, hat schon die normale Suche getroffen und die KI-Stufe lief nie.
    if schluessel == name.lower():
        return False

    try:
        from database import get_db_session

        async with get_db_session() as session:
            # Zwei Nutzer können denselben Namen gleichzeitig auflösen. Der
            # zweite Schreibvorgang darf daran nicht scheitern -- das Ergebnis
            # ist ja dasselbe.
            vorhanden = (await session.execute(
                text("SELECT karten_name FROM kartenname_gedaechtnis "
                     "WHERE begriff = :b"), {"b": schluessel})).scalar()
            if vorhanden:
                if vorhanden != name:
                    # Zwei verschiedene Antworten auf dieselbe Eingabe. Der
                    # erste Eintrag bleibt stehen -- aber das gehört gemeldet:
                    # entweder hat sich Scryfall geändert, oder eine der
                    # beiden Zuordnungen ist falsch.
                    logger.warning(
                        "Kartennamen-Gedächtnis: %r ist bereits als %r bekannt, "
                        "jetzt kam %r. Der alte Eintrag bleibt.",
                        schluessel, vorhanden, name)
                return False

            await session.execute(
                text("INSERT INTO kartenname_gedaechtnis "
                     "(begriff, karten_name, quelle, treffer) "
                     "VALUES (:b, :n, :q, 0)"),
                {"b": schluessel, "n": name, "q": quelle})
            logger.info("Kartennamen-Gedächtnis: %r -> %r gemerkt (%s).",
                        schluessel, name, quelle)
            return True
    except Exception:
        logger.debug("Kartennamen-Gedächtnis nicht schreibbar", exc_info=True)
        return False


async def vergessen(begriff: str) -> bool:
    """Entfernt einen Eintrag -- für den Fall, dass doch einer falsch ist."""
    schluessel = _schluessel(begriff)
    if not schluessel:
        return False
    try:
        from database import get_db_session

        async with get_db_session() as session:
            ergebnis = await session.execute(
                text("DELETE FROM kartenname_gedaechtnis WHERE begriff = :b"),
                {"b": schluessel})
            return bool(ergebnis.rowcount)
    except Exception:
        logger.debug("Kartennamen-Gedächtnis nicht löschbar", exc_info=True)
        return False


async def stand() -> dict:
    """Wie viel weiss das Gedächtnis, und was hat es erspart?"""
    try:
        from database import get_db_session

        async with get_db_session() as session:
            zeile = (await session.execute(
                text("SELECT COUNT(*), COALESCE(SUM(treffer), 0) "
                     "FROM kartenname_gedaechtnis"))).first()
            return {"eintraege": int(zeile[0] or 0),
                    "ersparte_ki_anfragen": int(zeile[1] or 0)}
    except Exception:
        logger.debug("Kartennamen-Gedächtnis nicht abfragbar", exc_info=True)
        return {"eintraege": 0, "ersparte_ki_anfragen": 0}
