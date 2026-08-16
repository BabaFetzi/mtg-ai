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
GRANA_ENV = os.getenv("GRANA_ENV", "development").strip().lower()
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

# Simple in-memory rate limiter for login
# Key: (ip, username), Value: (attempts_count, block_until_timestamp)
login_attempts: Dict[Tuple[str, str], Tuple[int, float]] = {}

# Zeitpunkt des letzten Fehlversuchs je Schlüssel -- nötig, um alte Einträge
# wieder freizugeben. Ohne diese Bereinigung wuchs `login_attempts` unbegrenzt:
# wer Logins für viele verschiedene Benutzernamen/IPs durchprobiert, konnte den
# Serverspeicher volllaufen lassen (jede Kombination legte dauerhaft einen
# Eintrag an, der nie entfernt wurde).
_attempt_seen: Dict[Tuple[str, str], float] = {}
LOGIN_ATTEMPT_TTL_SECONDS = 3600
_MAX_TRACKED_ATTEMPTS = 10000

# Brute-Force-Schutz: nach MAX_LOGIN_ATTEMPTS Fehlversuchen wird die Kombination
# aus IP und Benutzername für LOGIN_BLOCK_SECONDS gesperrt.
MAX_LOGIN_ATTEMPTS = 5
LOGIN_BLOCK_SECONDS = 900  # 15 Minuten


def _prune_login_attempts(now: float) -> None:
    """Entfernt abgelaufene Fehlversuchs-Einträge (nicht mehr gesperrt und älter
    als LOGIN_ATTEMPT_TTL_SECONDS)."""
    veraltet = [
        key
        for key, seen in _attempt_seen.items()
        if now - seen > LOGIN_ATTEMPT_TTL_SECONDS
        and now >= login_attempts.get(key, (0, 0.0))[1]
    ]
    for key in veraltet:
        login_attempts.pop(key, None)
        _attempt_seen.pop(key, None)

def check_login_rate_limit(ip: str, username: str) -> None:
    key = (ip, username)
    now = time.time()
    if key in login_attempts:
        attempts, block_until = login_attempts[key]
        if now < block_until:
            wait_seconds = int(block_until - now)
            # In Minuten runden: "Bitte warte 843 Sekunden" ist für Nutzer
            # schwer einzuordnen.
            wait_minutes = max(1, round(wait_seconds / 60))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Zu viele Fehlversuche. Dieser Zugang ist noch etwa "
                    f"{wait_minutes} Minute{'n' if wait_minutes != 1 else ''} gesperrt."
                )
            )
        # Reset limit if block time has expired
        if now > block_until and attempts >= MAX_LOGIN_ATTEMPTS:
            login_attempts[key] = (0, 0.0)
            
def record_login_attempt(ip: str, username: str, success: bool) -> int:
    """Protokolliert einen Login-Versuch.

    Returns:
        Anzahl der noch verbleibenden Versuche vor der Sperre (bei Erfolg: MAX).
        Wird die Sperre ausgelöst, wird stattdessen eine HTTPException geworfen.
    """
    key = (ip, username)
    now = time.time()

    # Gelegentlich aufräumen: bei jedem Fehlversuch, sobald die Registry gross
    # wird -- so bleibt der Speicherverbrauch auch unter Angriff begrenzt.
    if len(login_attempts) > _MAX_TRACKED_ATTEMPTS:
        _prune_login_attempts(now)

    if success:
        login_attempts.pop(key, None)
        _attempt_seen.pop(key, None)
        return MAX_LOGIN_ATTEMPTS

    attempts, block_until = login_attempts.get(key, (0, 0.0))
    attempts += 1
    _attempt_seen[key] = now
    if attempts >= MAX_LOGIN_ATTEMPTS:
        block_until = now + LOGIN_BLOCK_SECONDS
        login_attempts[key] = (attempts, block_until)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Zu viele Fehlversuche. Der Login ist für "
                f"{LOGIN_BLOCK_SECONDS // 60} Minuten gesperrt."
            )
        )
    login_attempts[key] = (attempts, block_until)
    return MAX_LOGIN_ATTEMPTS - attempts

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
