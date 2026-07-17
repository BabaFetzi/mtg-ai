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

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET_KEY ist nicht gesetzt! Es wird ein zufälliger, "
        "flüchtiger Schlüssel für diesen Prozess verwendet – bestehende Tokens "
        "werden bei jedem Neustart ungültig und Tokens sind zwischen mehreren "
        "Workern nicht kompatibel. Setze JWT_SECRET_KEY in der Produktionsumgebung!"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)

# Simple in-memory rate limiter for login
# Key: (ip, username), Value: (attempts_count, block_until_timestamp)
login_attempts: Dict[Tuple[str, str], Tuple[int, float]] = {}

def check_login_rate_limit(ip: str, username: str) -> None:
    key = (ip, username)
    now = time.time()
    if key in login_attempts:
        attempts, block_until = login_attempts[key]
        if now < block_until:
            wait_time = int(block_until - now)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Zu viele Fehlversuche. Bitte warte {wait_time} Sekunden."
            )
        # Reset limit if block time has expired
        if now > block_until and attempts >= 5:
            login_attempts[key] = (0, 0.0)
            
def record_login_attempt(ip: str, username: str, success: bool) -> None:
    key = (ip, username)
    now = time.time()
    if success:
        if key in login_attempts:
            del login_attempts[key]
    else:
        attempts, block_until = login_attempts.get(key, (0, 0.0))
        attempts += 1
        if attempts >= 5:
            block_until = now + 900 # 15 minutes block
            login_attempts[key] = (attempts, block_until)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Zu viele Fehlversuche. Login für 15 Minuten gesperrt."
            )
        else:
            login_attempts[key] = (attempts, block_until)

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
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
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
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
