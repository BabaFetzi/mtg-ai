"""
services/limiter.py – Zentraler Rate-Limiter (slowapi)

Nutzt Redis als geteilten Storage-Backend, damit Limits über mehrere
Worker/Prozesse hinweg konsistent durchgesetzt werden. Ist REDIS_URL nicht
gesetzt ODER nicht erreichbar, fällt es auf slowapis In-Memory-Storage
zurück (nur für lokale Entwicklung geeignet, nicht für Multi-Worker-
Deployments) -- Erreichbarkeit wird vorab per ping() geprüft, analog zu
services/cache.py und services/usage_limiter.py. Ohne diesen Check würde
jede Rate-Limit-Prüfung zur Laufzeit mit ConnectionError abstürzen, sobald
REDIS_URL konfiguriert, Redis aber (z.B. durch einen Ausfall) gerade nicht
erreichbar ist.
"""

import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _resolve_storage_uri():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis
        client = redis.from_url(redis_url, socket_timeout=1)
        client.ping()
        return redis_url
    except Exception as fehler:
        # Kein Traceback: "kein Redis vorhanden" ist der Normalfall einer lokalen
        # Installation. Der volle Stack schrieb bei jedem Start 40 Zeilen ins Log
        # und liess einen harmlosen Fallback wie einen Absturz aussehen -- echte
        # Fehler gingen darin unter. Der Grund steht weiterhin in der Meldung.
        logger.warning(
            "Redis für Rate-Limiter nicht erreichbar (%s: %s) – nutze "
            "In-Memory-Fallback. Nur für lokale Entwicklung geeignet: bei "
            "mehreren Arbeitsprozessen zählt jeder Prozess für sich.",
            type(fehler).__name__, fehler,
        )
        return None


limiter = Limiter(key_func=get_remote_address, storage_uri=_resolve_storage_uri())
