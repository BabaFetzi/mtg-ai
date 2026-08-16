"""services/sperrliste.py -- Konten, deren Token nicht mehr gelten sollen.

Zugriffs- und Auffrischungs-Token werden beim Prüfen nur entschlüsselt, nicht
gegen die Datenbank gehalten. Nach einer Kontolöschung wäre der
Auffrischungs-Token deshalb noch bis zu 30 Tage brauchbar: das gelöschte Konto
könnte sich immer neue Zugriffstoken holen und damit Daten anlegen, die es laut
Löschung nicht mehr geben darf.

Warum ein eigenes Modul und nicht einfach in auth.py: der Zustand lebt im
Prozess. auth.py wird an einer Stelle im Test neu geladen (um das Verhalten bei
fehlendem JWT_SECRET_KEY zu prüfen), und dabei entstünden zwei Kopien dieser
Liste -- die Endpunkte benutzten die eine, das Aufräumen träfe die andere. Hier
gibt es sie genau einmal.

Die Liste wird höchstens alle FRISCHE_SEKUNDEN aus der Datenbank nachgeladen;
ein Datenbankzugriff pro Anfrage wäre bei tausenden Nutzern zu teuer. Die
Lücke ist damit auf diese Zeitspanne begrenzt und bewusst so gewählt.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

FRISCHE_SEKUNDEN = float(os.getenv("GESPERRT_FRISCHE_SEKUNDEN", "30"))

# Wie lange ein Sperrvermerk gebraucht wird: solange irgendein Token gelten
# kann. Danach ist er gegenstandslos.
GUELTIG_TAGE = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

_gesperrt: set = set()
_stand: float = 0.0


def sofort_sperren(benutzername: str) -> None:
    """Nimmt ein Konto ohne Umweg über die Datenbank auf.

    Damit wirkt die Löschung im eigenen Prozess sofort; andere Prozesse ziehen
    beim nächsten Nachladen nach.
    """
    if benutzername:
        _gesperrt.add(benutzername.strip().lower())


def zuruecksetzen() -> None:
    """Leert die Liste und erzwingt ein Nachladen -- für Tests."""
    global _stand
    _gesperrt.clear()
    _stand = 0.0


async def _aktuell() -> set:
    global _stand
    jetzt = time.time()
    if jetzt - _stand < FRISCHE_SEKUNDEN:
        return _gesperrt

    _stand = jetzt
    try:
        from sqlalchemy import text
        from database import get_db_session

        grenze = datetime.utcnow() - timedelta(days=GUELTIG_TAGE)
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT benutzername FROM geloeschte_konten WHERE geloescht_am > :grenze"),
                {"grenze": grenze},
            )
            frisch = {(r[0] or "").strip().lower() for r in res.fetchall()}
        _gesperrt.clear()
        _gesperrt.update(frisch)
    except Exception:
        # Fehlt die Tabelle (ältere Installation) oder ist die Datenbank kurz
        # weg, bleibt die zuletzt bekannte Liste stehen. Sie zu leeren wäre die
        # gefährlichere Reaktion.
        logger.debug("Sperrliste nicht ladbar", exc_info=True)
    return _gesperrt


async def ist_gesperrt(benutzername: str) -> bool:
    if not benutzername:
        return False
    return benutzername.strip().lower() in await _aktuell()
