"""
routers/auth.py – Benutzer-Registrierung, Login & OAuth2-Verbindungen

Endpoints:
    POST /api/register                    – Neuen Benutzer registrieren (mit bcrypt-Hashing)
    POST /api/login                       – Login mit Rate-Limiting und Hash-Migration (SHA-256 → bcrypt)
    GET  /api/user/role/{benutzername}    – Aktuelle Rolle eines Benutzers abfragen
    POST /api/user/update-role            – Benutzerrolle aktualisieren (z. B. nach Stripe-Checkout)
    GET  /api/auth/google/login           – Google OAuth-Login Weiterleitung
    GET  /api/auth/google/callback        – Google OAuth-Callback zur Benutzeranlage/Login
    GET  /api/auth/discord/login          – Discord OAuth-Login Weiterleitung
    GET  /api/auth/discord/callback       – Discord OAuth-Callback zur Benutzeranlage/Login

Abhängigkeiten:
    - database    → get_db_session()
    - auth        → bcrypt_hash, verify_passwort, create_access_token, create_refresh_token, check_login_rate_limit, record_login_attempt
    - schemas     → LoginData, UpdateRoleReq
"""

import os
import re
import time
import urllib.parse
import hashlib
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from database import get_db_session
from auth import (
    hash_passwort as bcrypt_hash,
    verify_passwort,
    create_access_token,
    create_refresh_token,
    check_login_rate_limit,
    record_login_attempt
)
from schemas.models import LoginData, UpdateRoleReq

# ======================================================================
# OAuth Konfiguration aus Umgebungsvariablen
# ======================================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/api/auth/discord/callback")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["Auth"],
)

# ======================================================================
# POST /api/register – Registrierung
# ======================================================================
@router.post(
    "/register",
    summary="Registriert einen neuen Benutzer",
)
async def register(data: LoginData):
    try:
        async with get_db_session() as session:
            # Prüfen, ob Benutzer bereits existiert
            res = await session.execute(
                text("SELECT benutzername FROM nutzer WHERE benutzername = :name"),
                {"name": data.benutzername}
            )
            if res.first():
                return {"erfolg": False, "error": "Benutzername schon vergeben."}
            
            # Passwort per bcrypt hashen (legacy SHA-256 wird beim Login migriert)
            hashed = bcrypt_hash(data.passwort)
            await session.execute(
                text("INSERT INTO nutzer (benutzername, passwort_hash, rolle) VALUES (:name, :pwhash, :role)"),
                {"name": data.benutzername, "pwhash": hashed, "role": "free"}
            )
        return {"erfolg": True}
    except Exception as e:
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# POST /api/login – Login mit Migration
# ======================================================================
@router.post(
    "/login",
    summary="Benutzer einloggen",
)
async def login(data: LoginData, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    
    # 1. Rate Limiting prüfen
    try:
        check_login_rate_limit(ip, data.benutzername)
    except HTTPException as limit_exc:
        return {"erfolg": False, "error": limit_exc.detail}

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM nutzer WHERE benutzername = :name"),
            {"name": data.benutzername}
        )
        row = res.mappings().first()
        
        if not row:
            record_login_attempt(ip, data.benutzername, success=False)
            return {"erfolg": False, "error": "Falscher Benutzername oder Passwort."}
            
        stored_hash = row["passwort_hash"]
        is_valid = False
        migrate_hash = False
        
        # Falls das Passwort mit dem alten SHA-256 Algorithmus gehasht wurde
        if stored_hash and len(stored_hash) == 64:
            legacy_hash = hashlib.sha256(str.encode(data.passwort)).hexdigest()
            if legacy_hash == stored_hash:
                is_valid = True
                migrate_hash = True
        else:
            if verify_passwort(data.passwort, stored_hash):
                is_valid = True
                
        if not is_valid:
            try:
                record_login_attempt(ip, data.benutzername, success=False)
            except HTTPException as block_exc:
                return {"erfolg": False, "error": block_exc.detail}
            return {"erfolg": False, "error": "Falscher Benutzername oder Passwort."}
            
        # Hash zu bcrypt migrieren
        if migrate_hash:
            new_hash = bcrypt_hash(data.passwort)
            await session.execute(
                text("UPDATE nutzer SET passwort_hash = :new_hash WHERE benutzername = :name"),
                {"new_hash": new_hash, "name": data.benutzername}
            )
            
        # Login-Versuch erfolgreich loggen
        record_login_attempt(ip, data.benutzername, success=True)
        
        # JWT Tokens generieren
        token_data = {"sub": row["benutzername"], "role": row["rolle"] or "free"}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return {
            "erfolg": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "benutzername": row["benutzername"],
            "rolle": row["rolle"] or "free"
        }

# ======================================================================
# GET /api/user/role/{benutzername} – Rolle abfragen
# ======================================================================
@router.get(
    "/user/role/{benutzername}",
    summary="Benutzerrolle abfragen",
)
async def get_user_role(benutzername: str):
    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT rolle FROM nutzer WHERE benutzername = :name"),
            {"name": benutzername}
        )
        row = res.mappings().first()
        if row:
            return {"rolle": row["rolle"] or "free"}
        return {"rolle": "free"}

# ======================================================================
# POST /api/user/update-role – Rolle manuell setzen
# ======================================================================
@router.post(
    "/user/update-role",
    summary="Benutzerrolle aktualisieren",
)
async def update_user_role(req: UpdateRoleReq):
    async with get_db_session() as session:
        await session.execute(
            text("UPDATE nutzer SET rolle = :role WHERE benutzername = :name"),
            {"role": req.rolle, "name": req.benutzername}
        )
    return {"erfolg": True, "rolle": req.rolle}

# ======================================================================
# Google OAuth2 Endpunkte
# ======================================================================
@router.get(
    "/auth/google/login",
    summary="Google Login Umleitung",
)
async def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured. Add GOOGLE_CLIENT_ID to .env")
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(GOOGLE_REDIRECT_URI)}&"
        f"scope=openid%20email%20profile&"
        f"response_type=code"
    )
    return RedirectResponse(url)

@router.get(
    "/auth/google/callback",
    summary="Google Login Callback",
)
async def google_callback(code: str):
    async with httpx.AsyncClient() as client:
        # 1. Code gegen Access Token tauschen
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve token from Google")
        token_data = resp.json()
        google_access_token = token_data.get("access_token")
        
        # 2. User Info abrufen
        resp_user = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
            "Authorization": f"Bearer {google_access_token}"
        })
        if resp_user.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google")
        user_info = resp_user.json()
        email = user_info.get("email")
        name = user_info.get("name") or email.split("@")[0]
        google_id = user_info.get("sub")
        
        # Username normalisieren
        username = re.sub(r'[^a-zA-Z0-9_]', '', name.replace(" ", "_"))
        
        # 3. In DB suchen oder anlegen
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM nutzer WHERE oauth_provider = 'google' AND oauth_id = :oid"),
                {"oid": google_id}
            )
            user_row = res.mappings().first()
            if not user_row:
                res_u = await session.execute(
                    text("SELECT * FROM nutzer WHERE benutzername = :name"),
                    {"name": username}
                )
                if res_u.first():
                    username = f"{username}_{int(time.time()) % 1000}"
                    
                await session.execute(
                    text("INSERT INTO nutzer (benutzername, email, oauth_provider, oauth_id, rolle) VALUES (:name, :email, 'google', :oid, 'free')"),
                    {"name": username, "email": email, "oid": google_id}
                )
                role = "free"
            else:
                username = user_row["benutzername"]
                role = user_row["rolle"] or "free"
                
        # 4. Anwendungs-JWT erzeugen
        jwt_token = create_access_token({"sub": username, "role": role})
        
        redirect_url = f"{FRONTEND_URL}/?status=success&user={username}&token={jwt_token}&role={role}"
        return RedirectResponse(redirect_url)

# ======================================================================
# Discord OAuth2 Endpunkte
# ======================================================================
@router.get(
    "/auth/discord/login",
    summary="Discord Login Umleitung",
)
async def discord_login():
    if not DISCORD_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Discord OAuth is not configured. Add DISCORD_CLIENT_ID to .env")
    url = (
        f"https://discord.com/api/oauth2/authorize?"
        f"client_id={DISCORD_CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(DISCORD_REDIRECT_URI)}&"
        f"scope=identify%20email&"
        f"response_type=code"
    )
    return RedirectResponse(url)

@router.get(
    "/auth/discord/callback",
    summary="Discord Login Callback",
)
async def discord_callback(code: str):
    async with httpx.AsyncClient() as client:
        # 1. Code tauschen
        resp = await client.post("https://discord.com/api/oauth2/token", data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": DISCORD_REDIRECT_URI
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to retrieve token from Discord: {resp.text}")
        token_data = resp.json()
        discord_access_token = token_data.get("access_token")
        
        # 2. User Info abrufen
        resp_user = await client.get("https://discord.com/api/users/@me", headers={
            "Authorization": f"Bearer {discord_access_token}"
        })
        if resp_user.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve user info from Discord")
        user_info = resp_user.json()
        email = user_info.get("email")
        name = user_info.get("username")
        discord_id = user_info.get("id")
        
        username = re.sub(r'[^a-zA-Z0-9_]', '', name)
        
        # 3. Speichern oder einloggen
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT * FROM nutzer WHERE oauth_provider = 'discord' AND oauth_id = :oid"),
                {"oid": discord_id}
            )
            user_row = res.mappings().first()
            if not user_row:
                res_u = await session.execute(
                    text("SELECT * FROM nutzer WHERE benutzername = :name"),
                    {"name": username}
                )
                if res_u.first():
                    username = f"{username}_{int(time.time()) % 1000}"
                    
                await session.execute(
                    text("INSERT INTO nutzer (benutzername, email, oauth_provider, oauth_id, rolle) VALUES (:name, :email, 'discord', :oid, 'free')"),
                    {"name": username, "email": email, "oid": discord_id}
                )
                role = "free"
            else:
                username = user_row["benutzername"]
                role = user_row["rolle"] or "free"
                
        # 4. JWT Access Token
        jwt_token = create_access_token({"sub": username, "role": role})
        
        redirect_url = f"{FRONTEND_URL}/?status=success&user={username}&token={jwt_token}&role={role}"
        return RedirectResponse(redirect_url)
