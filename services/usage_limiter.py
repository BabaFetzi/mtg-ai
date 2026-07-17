"""
services/usage_limiter.py – Monatliches KI-Nutzungslimit pro Nutzer

Begrenzt, wie oft ein einzelner Nutzer pro Kalendermonat kostenpflichtige
KI-Endpunkte aufrufen darf. Die bestehenden Minuten-Rate-Limits
(services/limiter.py) verhindern nur Bursts, nicht Dauerlast über Tage/Wochen --
siehe KI-Kosten-Audit: 10 Anfragen/Min über einen Monat ausgereizt wären
theoretisch >400k Aufrufe. Dieses Modul deckelt das zusätzlich pro Nutzer.

Nutzt denselben Redis-Server wie services/limiter.py (REDIS_URL). Ist Redis
nicht konfiguriert/erreichbar, wird NICHT durchgesetzt (fail-open) --
ein Redis-Ausfall soll das Produkt nicht für alle Nutzer lahmlegen.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MONTHLY_TEXT_LIMIT = 300
MONTHLY_VISION_MINUTES_LIMIT = 90.0

_USAGE_TTL_SECONDS = 60 * 60 * 24 * 35  # ~35 Tage, deckt jeden Kalendermonat ab

_redis_client = None
_redis_init_attempted = False


def _get_redis():
    """Lazy-Init, damit ein fehlendes REDIS_URL beim Import nicht crasht."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    _redis_init_attempted = True

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis
        client = redis.from_url(redis_url, socket_timeout=1)
        client.ping()
        _redis_client = client
    except Exception:
        logger.warning("Redis für KI-Nutzungslimit nicht verfügbar (Limit wird nicht durchgesetzt)", exc_info=True)
        _redis_client = None
    return _redis_client


def _month_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def check_and_increment_ai_usage(benutzername: str, limit: int = MONTHLY_TEXT_LIMIT) -> bool:
    """
    Erhöht den Monats-Zähler für Text-KI-Anfragen (Judge, Übersetzung,
    Deck-Analyse, Deck-Roast, Combo-Fallbacks) und gibt True zurück, wenn die
    Anfrage noch innerhalb des Limits liegt und ausgeführt werden darf.

    Fail-open: ohne Redis oder ohne benutzername wird nicht durchgesetzt.
    """
    if not benutzername:
        return True
    client = _get_redis()
    if client is None:
        return True

    key = f"ai_usage:{benutzername}:{_month_bucket()}"
    try:
        count = client.incr(key)
        client.expire(key, _USAGE_TTL_SECONDS)
        return count <= limit
    except Exception:
        logger.warning("Fehler beim Prüfen des KI-Nutzungslimits", exc_info=True)
        return True


def check_and_increment_vision_minutes(
    benutzername: str,
    minutes: float,
    limit: float = MONTHLY_VISION_MINUTES_LIMIT,
) -> bool:
    """
    Erhöht die genutzten Live-Vision-Minuten für benutzername im aktuellen
    Monat um `minutes` und gibt True zurück, wenn danach noch im Limit.

    Fail-open: ohne Redis oder ohne benutzername wird nicht durchgesetzt.
    """
    if not benutzername:
        return True
    client = _get_redis()
    if client is None:
        return True

    key = f"ai_vision_minutes:{benutzername}:{_month_bucket()}"
    try:
        total = client.incrbyfloat(key, minutes)
        client.expire(key, _USAGE_TTL_SECONDS)
        return float(total) <= limit
    except Exception:
        logger.warning("Fehler beim Prüfen des Vision-Nutzungslimits", exc_info=True)
        return True
