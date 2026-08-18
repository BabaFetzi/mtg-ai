"""
services/ai_usage_log.py – Protokoll aller KI-Anfragen (Tokens, Latenz, Kosten)

Warum: Bisher gab es nur einen Monatszähler. Damit ist nicht erkennbar, welche
Funktion wie oft fehlschlägt, wie lange sie braucht und was sie kostet -- die
Antwortqualität lässt sich so nur raten statt messen.

Aufbau:
- `record(...)` wird synchron aus dem KI-Adapter aufgerufen und legt den Eintrag
  nur in einen begrenzten Speicherpuffer. Es findet KEIN Datenbankzugriff im
  Antwortpfad statt -- eine KI-Antwort darf nie auf das Protokoll warten.
- `flush()` schreibt den Puffer gesammelt in die Datenbank und wird von einer
  Hintergrundaufgabe in main.py periodisch aufgerufen.

Datenschutz: Frage-/Antworttext nur bei AI_LOG_CONTENT=true (Standard: aus).
Kosten nur, wenn Preise über Umgebungsvariablen hinterlegt sind -- es werden
bewusst keine Preise geraten.
"""

import logging
import os
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Obergrenze des Puffers: lieber alte Telemetrie verwerfen als Speicher volllaufen
# lassen, falls die Datenbank längere Zeit nicht erreichbar ist.
MAX_BUFFER = int(os.getenv("AI_LOG_MAX_BUFFER", "2000"))

# Aufbewahrungsdauer; das Aufräumen erledigt die Wartungsaufgabe in main.py.
AI_LOG_RETENTION_DAYS = int(os.getenv("AI_LOG_RETENTION_DAYS", "30"))


def _log_content_enabled() -> bool:
    """Bei jedem Aufruf neu lesen, damit sich das Flag ohne Neustart ändern lässt."""
    return os.getenv("AI_LOG_CONTENT", "").strip().lower() in {"1", "true", "yes", "on"}


def berechne_kosten_usd(prompt_tokens: Optional[int], antwort_tokens: Optional[int],
                        modell: Optional[str] = None) -> Optional[float]:
    """
    Kosten dieses Aufrufs, je nach Modell.

    Die Preise stehen in services/ai_preise.py -- dort und nur dort, damit
    das Protokoll und werkzeuge/ki_kosten.py nie mit verschiedenen Zahlen
    rechnen. Je Modell, weil zwischen dem grossen und dem kleinen Modell
    Faktor 20 und mehr liegen kann.

    Gibt None zurück, wenn für dieses Modell kein Preis hinterlegt ist -- ein
    geratener Preis wäre schlimmer als gar keiner.
    """
    from services.ai_preise import kosten

    return kosten(prompt_tokens, antwort_tokens, modell)


_buffer: "deque[Dict[str, Any]]" = deque(maxlen=MAX_BUFFER)
_lock = threading.Lock()


def record(
    *,
    funktion: str,
    modell: str,
    erfolg: bool,
    latenz_ms: int,
    benutzername: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    antwort_tokens: Optional[int] = None,
    gesamt_tokens: Optional[int] = None,
    fehler: Optional[str] = None,
    frage: Optional[str] = None,
    antwort: Optional[str] = None,
) -> None:
    """Legt einen Protokolleintrag in den Puffer (kein Datenbankzugriff)."""
    eintrag = {
        "benutzername": benutzername or None,
        "funktion": (funktion or "unbekannt")[:50],
        "modell": (modell or "")[:80],
        "erfolg": bool(erfolg),
        "fehler": (fehler[:2000] if fehler else None),
        "prompt_tokens": prompt_tokens,
        "antwort_tokens": antwort_tokens,
        "gesamt_tokens": gesamt_tokens,
        "latenz_ms": int(latenz_ms),
        "kosten_usd": berechne_kosten_usd(prompt_tokens, antwort_tokens, modell),
        "frage": (frage[:8000] if (frage and _log_content_enabled()) else None),
        "antwort": (antwort[:8000] if (antwort and _log_content_enabled()) else None),
        "erstellt_am": datetime.utcnow(),
    }
    with _lock:
        _buffer.append(eintrag)


def _drain() -> List[Dict[str, Any]]:
    with _lock:
        eintraege = list(_buffer)
        _buffer.clear()
    return eintraege


def buffered_count() -> int:
    with _lock:
        return len(_buffer)


async def flush() -> int:
    """Schreibt gepufferte Einträge gesammelt in die Datenbank.

    Returns:
        Anzahl geschriebener Einträge.
    """
    eintraege = _drain()
    if not eintraege:
        return 0

    from sqlalchemy import text as sql_text
    from database import get_db_session

    try:
        async with get_db_session() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO ai_calls "
                    "(benutzername, funktion, modell, erfolg, fehler, prompt_tokens, "
                    " antwort_tokens, gesamt_tokens, latenz_ms, kosten_usd, frage, antwort, erstellt_am) "
                    "VALUES (:benutzername, :funktion, :modell, :erfolg, :fehler, :prompt_tokens, "
                    " :antwort_tokens, :gesamt_tokens, :latenz_ms, :kosten_usd, :frage, :antwort, :erstellt_am)"
                ),
                eintraege,
            )
        return len(eintraege)
    except Exception:
        logger.warning("KI-Protokoll konnte nicht geschrieben werden (%d Einträge verworfen)",
                       len(eintraege), exc_info=True)
        return 0


async def purge_old(retention_days: Optional[int] = None) -> int:
    """Löscht Protokolleinträge, die älter als die Aufbewahrungsfrist sind."""
    days = AI_LOG_RETENTION_DAYS if retention_days is None else retention_days
    if days <= 0:
        return 0

    from sqlalchemy import text as sql_text
    from database import get_db_session

    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        async with get_db_session() as session:
            res = await session.execute(
                sql_text("DELETE FROM ai_calls WHERE erstellt_am < :cutoff"),
                {"cutoff": cutoff},
            )
        return res.rowcount or 0
    except Exception:
        logger.warning("Aufräumen des KI-Protokolls fehlgeschlagen", exc_info=True)
        return 0
