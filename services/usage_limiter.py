"""
services/usage_limiter.py – Monatliches KI-Nutzungslimit pro Nutzer

Begrenzt, wie oft ein einzelner Nutzer pro Kalendermonat kostenpflichtige
KI-Endpunkte aufrufen darf. Die Minuten-Rate-Limits (services/limiter.py)
verhindern nur Bursts, nicht Dauerlast über Tage und Wochen -- 10 Anfragen pro
Minute einen Monat lang ausgereizt wären über 400 000 Aufrufe. Dieses Modul
deckelt das zusätzlich pro Nutzer.

Warum die Datenbank und nicht Redis
-----------------------------------
Der Zähler lag früher ausschliesslich in Redis, mit einem ausdrücklichen
"fail-open": kein REDIS_URL oder Redis nicht erreichbar hiess **gar kein
Limit**. Das war als Freundlichkeit gedacht (ein Redis-Ausfall soll das Produkt
nicht lahmlegen), war aber die teuerste Stelle der Anwendung: jeder
Gemini-Aufruf kostet Geld, und ein vergessenes REDIS_URL hätte unbegrenzte
Kosten verursacht, ohne dass irgendetwas auffällt.

Jetzt zählt die Datenbank. Sie ist ohnehin da -- läuft sie nicht, läuft die
Anwendung nicht. Damit gilt der Zähler über alle Worker hinweg, übersteht einen
Neustart, und es gibt nur EINE Wahrheit statt zweier, die auseinanderlaufen
können.

Der Geschwindigkeitsvorteil von Redis spielt hier keine Rolle: gezählt wird
unmittelbar vor einem KI-Aufruf, der Sekunden dauert. Ein UPSERT von etwa einer
Millisekunde fällt daneben nicht ins Gewicht. Bei Live-Vision wird höchstens
alle 12,5 Sekunden gezählt.

Redis bleibt für die Drosselung in services/limiter.py zuständig -- dort zählt
jede Anfrage, und dort ist Tempo tatsächlich wichtig.

Verhalten im Fehlerfall
-----------------------
Schlägt der Datenbankzugriff fehl, wird der Aufruf ZUGELASSEN und die Störung
protokolliert. Das ist bewusst so: eine kurzzeitig klemmende Datenbank soll
zahlende Nutzer nicht aussperren. Anders als vorher ist das aber der seltene
Ausnahmefall und nicht der Normalzustand einer Installation ohne Redis.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

MONTHLY_TEXT_LIMIT = 300
MONTHLY_VISION_MINUTES_LIMIT = 90.0

ART_TEXT = "text"
ART_VISION = "vision"

# Ein einziger Schritt: anlegen oder erhöhen, und der neue Stand kommt zurück.
# Zwei getrennte Schritte (lesen, dann schreiben) hätten bei gleichzeitigen
# Anfragen desselben Nutzers Aufrufe verschluckt -- genau die Situation, die
# ein Limit verhindern soll.
#
# ON CONFLICT ... DO UPDATE ... RETURNING versteht sowohl SQLite (ab 3.35) als
# auch PostgreSQL.
_ERHOEHEN = text("""
    INSERT INTO ki_nutzung (benutzername, monat, art, wert, erstellt_am)
    VALUES (:benutzername, :monat, :art, :menge, :jetzt)
    ON CONFLICT (benutzername, monat, art)
    DO UPDATE SET wert = ki_nutzung.wert + :menge
    RETURNING wert
""")


def _monat() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _erhoehen(benutzername: str, art: str, menge: float) -> Optional[float]:
    """Erhöht den Monatswert und liefert den neuen Stand, oder None bei Störung."""
    # Erst hier importieren: services/ wird von database.py-nahen Modulen
    # eingebunden, ein Import auf Modulebene würde einen Ringschluss erzeugen.
    from database import get_db_session

    try:
        async with get_db_session() as session:
            res = await session.execute(_ERHOEHEN, {
                "benutzername": benutzername,
                "monat": _monat(),
                "art": art,
                "menge": menge,
                "jetzt": datetime.now(timezone.utc),
            })
            stand = res.scalar_one()
        return float(stand)
    except Exception:
        logger.warning("KI-Nutzungslimit konnte nicht gezählt werden (Aufruf wird "
                       "zugelassen)", exc_info=True)
        return None


async def check_and_increment_ai_usage(benutzername: str,
                                       limit: int = MONTHLY_TEXT_LIMIT) -> bool:
    """Zählt eine Text-KI-Anfrage und sagt, ob sie noch im Limit liegt.

    Betrifft Judge, Übersetzung, Deck-Analyse, Deck-Roast und die
    Combo-Rückfallebene.
    """
    if not benutzername:
        return True
    stand = await _erhoehen(benutzername, ART_TEXT, 1)
    if stand is None:
        return True
    return stand <= limit


async def check_and_increment_vision_minutes(
    benutzername: str,
    minutes: float,
    limit: float = MONTHLY_VISION_MINUTES_LIMIT,
) -> bool:
    """Rechnet `minutes` auf das Live-Vision-Kontingent an."""
    if not benutzername:
        return True
    stand = await _erhoehen(benutzername, ART_VISION, minutes)
    if stand is None:
        return True
    return stand <= limit


async def stand_abfragen(benutzername: str, art: str = ART_TEXT) -> float:
    """Aktueller Monatsstand, ohne ihn zu erhöhen. Für Anzeige und Tests."""
    from database import get_db_session

    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT wert FROM ki_nutzung WHERE benutzername = :b "
                     "AND monat = :m AND art = :a"),
                {"b": benutzername, "m": _monat(), "a": art})
            zeile = res.scalar_one_or_none()
        return float(zeile or 0.0)
    except Exception:
        logger.warning("KI-Nutzungsstand nicht lesbar", exc_info=True)
        return 0.0


async def alte_monate_aufraeumen(behalten: int = 3) -> int:
    """Löscht Zählerstände, die älter als `behalten` Monate sind.

    Ohne das wächst die Tabelle mit jedem Monat und Nutzer weiter, obwohl nur
    der laufende Monat gebraucht wird. Ein paar Monate bleiben stehen, damit
    man einen Verbrauchsverlauf hat.
    """
    from database import get_db_session

    jetzt = datetime.now(timezone.utc)
    monat = jetzt.month - behalten
    jahr = jetzt.year
    while monat <= 0:
        monat += 12
        jahr -= 1
    grenze = f"{jahr:04d}-{monat:02d}"

    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("DELETE FROM ki_nutzung WHERE monat < :grenze"),
                {"grenze": grenze})
        return res.rowcount or 0
    except Exception:
        logger.warning("Alte KI-Zählerstände nicht aufräumbar", exc_info=True)
        return 0
