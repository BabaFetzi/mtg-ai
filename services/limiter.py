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

from services import umgebung

logger = logging.getLogger(__name__)


def _resolve_storage_uri():
    redis_url = umgebung.roh("REDIS_URL")
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


# Hinter einem Reverse-Proxy (nginx, Caddy, Cloudflare -- also überall, wo TLS
# terminiert wird) ist request.client.host die Adresse des PROXYS. Mit
# get_remote_address teilen sich dann ALLE Nutzer der Welt ein einziges
# Kontingent: 30 Anfragen pro Minute für die gesamte Seite. Im Lasttest waren
# bei 25 gleichzeitigen Nutzern 88 Prozent der Deck-Aufrufe HTTP 429.
#
# Deshalb wird nach Möglichkeit der angemeldete Nutzer als Schlüssel genommen.
# Das ist auch fairer: ein Nutzer kann andere nicht mehr aussperren, egal wie
# viele hinter derselben Adresse sitzen (Wohnung, Firma, Mobilfunk).
def _weiterleitungs_ip(request) -> str:
    """Adresse aus X-Forwarded-For -- nur, wenn dem Proxy vertraut wird.

    Ohne dieses Vertrauen könnte jeder die Kopfzeile selbst setzen und damit
    das Limit umgehen. Standard ist deshalb aus.
    """
    # umgebung.schalter statt eines eigenen Vergleichs: es meldet einen
    # unverstandenen Wert ("ture") ins Protokoll, statt ihn still als "aus" zu
    # lesen. Der Standard bleibt aus -- ein versehentlich vertrauter Proxy
    # waere eine Luecke in der Drosselung.
    if not umgebung.schalter("TRUST_PROXY_HEADERS", False):
        return ""
    kette = request.headers.get("x-forwarded-for", "")
    # Der erste Eintrag ist der ursprüngliche Absender.
    return kette.split(",")[0].strip()


def limit_schluessel(request) -> str:
    """Angemeldeter Nutzer, sonst Adresse."""
    kopf = request.headers.get("authorization", "")
    if kopf.lower().startswith("bearer "):
        try:
            from auth import decode_token
            nutzdaten = decode_token(kopf.split(" ", 1)[1].strip())
            if nutzdaten and nutzdaten.get("sub"):
                return f"nutzer:{nutzdaten['sub']}"
        except Exception:
            # Ein kaputtes Token darf die Drosselung nicht sprengen -- dann
            # zählt eben die Adresse.
            pass
    return f"ip:{_weiterleitungs_ip(request) or get_remote_address(request)}"


limiter = Limiter(key_func=limit_schluessel, storage_uri=_resolve_storage_uri())
