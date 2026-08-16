"""services/anmeldeversuche.py -- Brute-Force-Schutz für den Login.

Nach MAX_VERSUCHE Fehlversuchen wird die Kombination aus IP und Benutzername
für SPERRE_SEKUNDEN gesperrt.

Warum das nicht im Prozessspeicher liegen darf
----------------------------------------------
Der Zähler war ein Dictionary im Modul. Damit hatte jeder uvicorn-Worker seinen
eigenen: bei den empfohlenen 2 Workern wurden aus 5 erlaubten Fehlversuchen
faktisch 10, bei 4 Workern 20 -- und niemand hätte es gemerkt, weil die Sperre
ja "funktioniert". Ein Neustart löschte zudem alle Sperren, ein Angreifer musste
also nur auf das nächste Deployment warten.

Jetzt zählt die Datenbank. Sie ist beim Login ohnehin im Spiel (der Nutzer muss
nachgeschlagen werden), und die Passwortprüfung mit bcrypt dauert ein
Vielfaches der beiden kleinen Abfragen.

Eigenes Modul, nicht in auth.py
-------------------------------
Genau wie services/sperrliste.py: tests/test_jwt_secret.py lädt `auth` neu, um
den Schlüssel zu prüfen. Läge der Zustand dort, gäbe es danach zwei Kopien
davon -- ein Fehler, der nur im Zusammenspiel der Testdateien auftritt und
einzeln nie zu sehen ist.
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import text

logger = logging.getLogger(__name__)

MAX_VERSUCHE = 5
SPERRE_SEKUNDEN = 900          # 15 Minuten
# Nach dieser Zeit ohne neuen Fehlversuch verfällt der Zähler. Ohne das wäre
# ein einzelner Tippfehler vor Wochen noch Teil des Kontingents.
VERFALL_SEKUNDEN = 3600


def _sperrmeldung(restsekunden: float) -> HTTPException:
    minuten = max(1, round(restsekunden / 60))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(f"Zu viele Fehlversuche. Dieser Zugang ist noch etwa "
                f"{minuten} Minute{'n' if minuten != 1 else ''} gesperrt."),
    )


async def _zeile(session, ip: str, benutzername: str):
    res = await session.execute(
        text("SELECT versuche, gesperrt_bis, zuletzt FROM anmeldeversuche "
             "WHERE ip = :ip AND benutzername = :b"),
        {"ip": ip, "b": benutzername})
    return res.mappings().first()


async def pruefen(ip: str, benutzername: str) -> None:
    """Wirft 429, wenn diese Kombination gerade gesperrt ist."""
    from database import get_db_session

    try:
        async with get_db_session() as session:
            zeile = await _zeile(session, ip, benutzername)
    except Exception:
        # Ist die Datenbank nicht erreichbar, scheitert der Login ohnehin am
        # Nachschlagen des Nutzers. Hier zu blockieren brächte nichts.
        logger.warning("Anmeldeversuche nicht prüfbar", exc_info=True)
        return

    if not zeile:
        return
    rest = float(zeile["gesperrt_bis"] or 0) - time.time()
    if rest > 0:
        raise _sperrmeldung(rest)


async def merken(ip: str, benutzername: str, erfolg: bool) -> int:
    """Verbucht einen Versuch.

    Returns:
        Verbleibende Versuche bis zur Sperre (bei Erfolg: MAX_VERSUCHE).
        Löst der Versuch die Sperre aus, wird stattdessen 429 geworfen.
    """
    from database import get_db_session

    jetzt = time.time()
    try:
        async with get_db_session() as session:
            if erfolg:
                await session.execute(
                    text("DELETE FROM anmeldeversuche WHERE ip = :ip AND benutzername = :b"),
                    {"ip": ip, "b": benutzername})
                return MAX_VERSUCHE

            zeile = await _zeile(session, ip, benutzername)
            versuche = int(zeile["versuche"]) if zeile else 0
            gesperrt_bis = float(zeile["gesperrt_bis"] or 0) if zeile else 0.0
            zuletzt = float(zeile["zuletzt"] or 0) if zeile else 0.0

            # Abgelaufene Sperre und alte Zählerstände beginnen von vorn.
            if gesperrt_bis and jetzt >= gesperrt_bis:
                versuche, gesperrt_bis = 0, 0.0
            elif zuletzt and jetzt - zuletzt > VERFALL_SEKUNDEN:
                versuche = 0

            versuche += 1
            if versuche >= MAX_VERSUCHE:
                gesperrt_bis = jetzt + SPERRE_SEKUNDEN

            await session.execute(
                text("INSERT INTO anmeldeversuche (ip, benutzername, versuche, "
                     "gesperrt_bis, zuletzt) "
                     "VALUES (:ip, :b, :v, :g, :z) "
                     "ON CONFLICT (ip, benutzername) DO UPDATE SET "
                     "versuche = :v, gesperrt_bis = :g, zuletzt = :z"),
                {"ip": ip, "b": benutzername, "v": versuche,
                 "g": gesperrt_bis, "z": jetzt})
    except HTTPException:
        raise
    except Exception:
        logger.warning("Anmeldeversuch nicht speicherbar", exc_info=True)
        return MAX_VERSUCHE

    if versuche >= MAX_VERSUCHE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(f"Zu viele Fehlversuche. Der Login ist für "
                    f"{SPERRE_SEKUNDEN // 60} Minuten gesperrt."),
        )
    return MAX_VERSUCHE - versuche


async def aufraeumen() -> int:
    """Entfernt abgelaufene Einträge.

    Ohne das wüchse die Tabelle mit jeder durchprobierten Kombination weiter --
    genau das, was ein Angreifer massenhaft erzeugt. Noch laufende Sperren
    bleiben stehen.
    """
    from database import get_db_session

    jetzt = time.time()
    try:
        async with get_db_session() as session:
            res = await session.execute(
                text("DELETE FROM anmeldeversuche "
                     "WHERE zuletzt < :verfallen AND gesperrt_bis < :jetzt"),
                {"verfallen": jetzt - VERFALL_SEKUNDEN, "jetzt": jetzt})
        return res.rowcount or 0
    except Exception:
        logger.warning("Anmeldeversuche nicht aufräumbar", exc_info=True)
        return 0
