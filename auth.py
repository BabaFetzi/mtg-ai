import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from jose import jwt, JWTError
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

load_dotenv()

from services import umgebung

logger = logging.getLogger(__name__)

# Mindestlänge für den Token-Schlüssel. HS256 arbeitet mit einem 256-Bit-
# Geheimnis; alles darunter schwächt die Signatur messbar ab.
MIN_SECRET_LAENGE = 32

# In der Produktion darf ein fehlender Schlüssel den Start NICHT überleben.
# Vorher war es nur eine Warnung -- und genau deshalb lief die Anwendung mit
# einem flüchtigen Zufallsschlüssel: bei jedem Neustart wurden alle Anmeldungen
# ungültig, und mit mehreren Arbeitsprozessen schlug die Anmeldung sporadisch
# im laufenden Betrieb fehl, weil Worker A ein Token nicht prüfen konnte, das
# Worker B ausgestellt hatte. Eine Warnung, die man überlesen kann, ist hier
# keine Absicherung.
#
# umgebung.text statt os.getenv: bei "GRANA_ENV=" (leer, wie in einer kopierten
# .env.example) liefert os.getenv "" statt des Standards. Hier wäre das
# besonders unangenehm -- die Anwendung liefe dann im Entwicklungsmodus, und
# genau die Pflichtprüfung unten bliebe still aus.
GRANA_ENV = umgebung.text("GRANA_ENV", "development").lower()
IST_PRODUKTION = GRANA_ENV in {"production", "prod", "produktion"}

_SCHLUESSEL_HINWEIS = (
    "Erzeuge einen Schlüssel mit\n"
    "    python -c \"import secrets; print(secrets.token_hex(32))\"\n"
    "und trage ihn als JWT_SECRET_KEY in die .env ein."
)

SECRET_KEY = (os.getenv("JWT_SECRET_KEY") or "").strip()

if not SECRET_KEY:
    if IST_PRODUKTION:
        raise RuntimeError(
            "JWT_SECRET_KEY fehlt, GRANA_ENV steht aber auf Produktion. Ohne "
            "festen Schlüssel wird jede Anmeldung beim nächsten Neustart "
            "ungültig.\n" + _SCHLUESSEL_HINWEIS
        )
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET_KEY ist nicht gesetzt! Es wird ein zufälliger, flüchtiger "
        "Schlüssel für diesen Prozess verwendet – bestehende Anmeldungen werden "
        "bei jedem Neustart ungültig und sind zwischen mehreren Workern nicht "
        "kompatibel.\n%s", _SCHLUESSEL_HINWEIS,
    )
elif len(SECRET_KEY) < MIN_SECRET_LAENGE:
    if IST_PRODUKTION:
        raise RuntimeError(
            f"JWT_SECRET_KEY ist mit {len(SECRET_KEY)} Zeichen zu kurz "
            f"(mindestens {MIN_SECRET_LAENGE}).\n" + _SCHLUESSEL_HINWEIS
        )
    logger.warning(
        "JWT_SECRET_KEY ist mit %d Zeichen kürzer als die empfohlenen %d Zeichen.",
        len(SECRET_KEY), MIN_SECRET_LAENGE,
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)

# Gesperrte (gelöschte) Konten: die Liste lebt in services/sperrliste.py --
# dort gibt es sie genau einmal, auch wenn dieses Modul neu geladen wird.
from services.sperrliste import (  # noqa: E402
    ist_gesperrt,
    sofort_sperren as konto_sofort_sperren,
)

# ======================================================================
# Brute-Force-Schutz für den Login
# ======================================================================
# Lag früher als Dictionary in diesem Modul. Mit mehreren uvicorn-Workern hatte
# damit jeder Worker seinen eigenen Zähler (aus 5 erlaubten Fehlversuchen
# wurden bei 2 Workern faktisch 10), und ein Neustart löschte alle Sperren.
# Der Zustand liegt jetzt in der Datenbank -- siehe services/anmeldeversuche.py.
#
# Die Namen bleiben hier verfügbar, damit Aufrufer und Tests nicht wissen
# müssen, wo gezählt wird.
from services.anmeldeversuche import (  # noqa: E402
    MAX_VERSUCHE as MAX_LOGIN_ATTEMPTS,
    SPERRE_SEKUNDEN as LOGIN_BLOCK_SECONDS,
    VERFALL_SEKUNDEN as LOGIN_ATTEMPT_TTL_SECONDS,
    aufraeumen as aufraeumen_anmeldeversuche,
    merken as record_login_attempt,
    pruefen as check_login_rate_limit,
)

# Hashing utilities
def hash_passwort(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_passwort(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

# JWT utilities
#
# Access- und Refresh-Tokens tragen einen "type"-Claim, damit sie nicht
# austauschbar sind: ein (30 Tage gültiges) Refresh-Token darf NIE als
# Access-Token auf geschützten Endpunkten akzeptiert werden, und der
# /api/auth/refresh-Endpoint akzeptiert ausschliesslich echte Refresh-Tokens.
# Alt-Tokens ohne "type"-Claim (vor dieser Änderung ausgestellt) werden als
# Access-Token weiterbehandelt, damit eingeloggte Nutzer nicht schlagartig
# rausfliegen -- sie laufen ohnehin binnen 30 Minuten bzw. 30 Tagen aus.
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# Dependency to get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    if not token:
        # Fallback to check Authorization header manually in case OAuth2PasswordBearer parser is skipped
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht authentifiziert",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token oder Token abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Refresh-Tokens sind auf geschützten Endpunkten nicht gültig (nur auf
    # /api/auth/refresh). Fehlender type-Claim = Alt-Token = Access.
    if payload.get("type", "access") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh-Token ist kein gültiges Access-Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Gelöschtes Konto: das Token ist rechnerisch noch gültig, das Konto gibt es
    # aber nicht mehr. Ohne diese Prüfung liessen sich damit weiter Daten
    # anlegen -- die Löschung wäre nur halb passiert.
    if await ist_gesperrt(username):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dieses Konto wurde gelöscht.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

# Dependency für Endpunkte, die anonyme Nutzung weiterhin erlauben (z.B.
# Kartensuche), aber eine mitgeschickte Identität nicht mehr blind vom
# Client übernehmen dürfen. Gibt None zurück statt 401 zu werfen, wenn kein
# oder ein ungültiges Token vorhanden ist -- im Gegensatz zu get_current_user.
async def get_current_user_optional(token: str = Depends(oauth2_scheme)) -> Optional[str]:
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type", "access") != "access":
        return None
    benutzer = payload.get("sub")
    # Auch hier: ein gelöschtes Konto soll nicht als angemeldet gelten.
    if benutzer and await ist_gesperrt(benutzer):
        return None
    return benutzer
