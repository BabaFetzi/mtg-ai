"""
routers/auth.py – Benutzer-Registrierung, Login & OAuth2-Verbindungen

Endpoints:
    POST /api/register                    – Neuen Benutzer registrieren (mit bcrypt-Hashing)
    POST /api/login                       – Login mit Rate-Limiting und Hash-Migration (SHA-256 → bcrypt)
    GET  /api/user/role/{benutzername}    – Aktuelle Rolle eines Benutzers abfragen
    POST /api/user/update-role            – Eigene Rolle ändern oder (als Admin) fremde Rolle setzen; Premium ist per Self-Service gesperrt
    GET  /api/auth/google/login           – Google OAuth-Login Weiterleitung
    GET  /api/auth/google/callback        – Google OAuth-Callback zur Benutzeranlage/Login
    GET  /api/auth/discord/login          – Discord OAuth-Login Weiterleitung
    GET  /api/auth/discord/callback       – Discord OAuth-Callback zur Benutzeranlage/Login

Abhängigkeiten:
    - database    → get_db_session()
    - auth        → bcrypt_hash, verify_passwort, create_access_token, create_refresh_token, check_login_rate_limit, record_login_attempt
    - schemas     → LoginData, UpdateRoleReq
"""

import asyncio
import hashlib
import logging
import os
import re
import time
import urllib.parse
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db_session
from auth import (
    hash_passwort as bcrypt_hash,
    verify_passwort,
    create_access_token,
    create_refresh_token,
    decode_token,
    check_login_rate_limit,
    record_login_attempt,
    get_current_user,
    ist_gesperrt,
)
from schemas.models import LoginData, RegisterData, UpdateRoleReq

# ======================================================================
# OAuth Konfiguration aus Umgebungsvariablen
# ======================================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8001/api/auth/google/callback")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8001/api/auth/discord/callback")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5175")

# ======================================================================
# Router-Instanz
# ======================================================================
logger = logging.getLogger(__name__)

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
async def register(data: RegisterData):
    email = (data.email or "").strip().lower()
    # Einfache, robuste Format-Prüfung ohne zusätzliche Abhängigkeit.
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return {"erfolg": False, "error": "Bitte gib eine gültige E-Mail-Adresse ein."}
    try:
        async with get_db_session() as session:
            # Prüfen, ob Benutzername bereits existiert
            res = await session.execute(
                text("SELECT benutzername FROM nutzer WHERE benutzername = :name"),
                {"name": data.benutzername}
            )
            if res.first():
                return {"erfolg": False, "error": "Benutzername schon vergeben."}

            # Prüfen, ob die E-Mail bereits verwendet wird (Spalte ist unique)
            res_email = await session.execute(
                text("SELECT benutzername FROM nutzer WHERE email = :email"),
                {"email": email}
            )
            if res_email.first():
                return {"erfolg": False, "error": "Diese E-Mail-Adresse wird bereits verwendet."}

            # Passwort per bcrypt hashen (legacy SHA-256 wird beim Login migriert)
            hashed = bcrypt_hash(data.passwort)
            await session.execute(
                text("INSERT INTO nutzer (benutzername, email, passwort_hash, rolle) VALUES (:name, :email, :pwhash, :role)"),
                {"name": data.benutzername, "email": email, "pwhash": hashed, "role": "free"}
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
        await check_login_rate_limit(ip, data.benutzername)
    except HTTPException as limit_exc:
        return {"erfolg": False, "error": limit_exc.detail}

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT * FROM nutzer WHERE benutzername = :name"),
            {"name": data.benutzername}
        )
        row = res.mappings().first()
        
        if not row:
            await record_login_attempt(ip, data.benutzername, erfolg=False)
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
                verbleibend = await record_login_attempt(ip, data.benutzername, erfolg=False)
            except HTTPException as block_exc:
                return {"erfolg": False, "error": block_exc.detail}
            # Vor der Sperre warnen, statt den Nutzer unangekündigt für 15
            # Minuten auszusperren.
            fehler = "Falscher Benutzername oder Passwort."
            if verbleibend <= 2:
                fehler += (
                    f" Noch {verbleibend} Versuch{'e' if verbleibend != 1 else ''}, "
                    "danach wird der Login vorübergehend gesperrt."
                )
            return {"erfolg": False, "error": fehler}
            
        # Hash zu bcrypt migrieren
        if migrate_hash:
            new_hash = bcrypt_hash(data.passwort)
            await session.execute(
                text("UPDATE nutzer SET passwort_hash = :new_hash WHERE benutzername = :name"),
                {"new_hash": new_hash, "name": data.benutzername}
            )
            
        # Login-Versuch erfolgreich loggen
        await record_login_attempt(ip, data.benutzername, erfolg=True)
        
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
# POST /api/auth/refresh – Access-Token erneuern
# ======================================================================
class RefreshReq(BaseModel):
    refresh_token: str


@router.post(
    "/auth/refresh",
    summary="Access-Token per Refresh-Token erneuern",
)
async def refresh_access_token(req: RefreshReq):
    """
    Tauscht ein gültiges Refresh-Token gegen ein frisches Access-Token
    (plus rotiertes Refresh-Token), damit eingeloggte Nutzer nach Ablauf
    des 30-Minuten-Access-Tokens NICHT neu einloggen müssen.

    Sicherheit:
    - akzeptiert ausschliesslich Tokens mit type=="refresh" (ein Access-Token
      kann hier nicht eingetauscht werden)
    - prüft, dass der Benutzer noch existiert, und liest die Rolle FRISCH aus
      der DB -- ein zwischenzeitliches Premium-Upgrade/-Downgrade (z.B. durch
      den Stripe-Webhook) landet damit im nächsten Access-Token
    """
    payload = decode_token(req.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Refresh-Token.",
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Refresh-Token.",
        )

    # Ein Auffrischungs-Token gilt 30 Tage. Ohne diese Prüfung könnte sich ein
    # gelöschtes Konto damit einen Monat lang immer neue Zugriffstoken holen.
    if await ist_gesperrt(username):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dieses Konto wurde gelöscht.",
        )

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT benutzername, rolle FROM nutzer WHERE benutzername = :name"),
            {"name": username},
        )
        row = res.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer existiert nicht mehr.",
        )

    role = row["rolle"] or "free"
    token_data = {"sub": row["benutzername"], "role": role}
    return {
        "erfolg": True,
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "benutzername": row["benutzername"],
        "rolle": role,
    }


# ======================================================================
# GET /api/user/role/{benutzername} – Rolle abfragen
# ======================================================================
@router.get(
    "/user/role/{benutzername}",
    summary="Benutzerrolle abfragen",
)
async def get_user_role(benutzername: str, current_user: str = Depends(get_current_user)):
    # Zuvor war der Endpunkt völlig offen: damit liess sich für JEDEN
    # Benutzernamen prüfen, ob er existiert und ob er zahlender Kunde ist
    # (Konto-Enumeration + Offenlegung des Abo-Status). Jetzt darf nur der
    # eigene Status abgefragt werden -- Admins zusätzlich fremde.
    if benutzername != current_user and not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Du darfst nur deinen eigenen Status abfragen.",
        )
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
def _is_admin(username: str) -> bool:
    """Liest ADMIN_USERNAMES bei jedem Aufruf neu (kommagetrennte Liste), damit
    Admin-Rechte ohne Neustart des Prozesses vergeben/entzogen werden können."""
    admin_usernames = {
        u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()
    }
    return username in admin_usernames

@router.post(
    "/user/update-role",
    summary="Benutzerrolle aktualisieren",
)
async def update_user_role(req: UpdateRoleReq, current_user: str = Depends(get_current_user)):
    is_admin = _is_admin(current_user)
    is_self = current_user == req.benutzername

    if not is_admin and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Du darfst nur deine eigene Rolle ändern."
        )

    if not is_admin and req.rolle == "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium kann nicht selbst zugewiesen werden. Das Upgrade erfolgt automatisch nach erfolgreicher Zahlung."
        )

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


# ======================================================================
# Passwort vergessen / zurücksetzen
# ======================================================================
# Bis hierher gab es keinen Weg zurück ins eigene Konto: Wer sein Passwort
# verlor, verlor seine Sammlung. Bei einem Bezahlprodukt ist das ein
# garantierter Supportfall und ein Rückerstattungsgrund.
#
# Zwei Grundsätze prägen die Umsetzung:
#
# 1. KEINE Auskunft darüber, ob es ein Konto gibt. Beide Endpunkte antworten
#    immer gleich. Sonst wird "Passwort vergessen" zum Werkzeug, um gültige
#    E-Mail-Adressen und Benutzernamen durchzuprobieren.
# 2. In der Datenbank steht nur der HASH des Tokens. Wer sie liest, kann daraus
#    kein gültiges Token bauen -- dieselbe Überlegung wie beim Passwort.

RESET_GUELTIG_MINUTEN = int(os.getenv("PASSWORT_RESET_MINUTEN", "60"))
MIN_PASSWORT_LAENGE = 8

# Immer dieselbe Antwort, egal ob es das Konto gibt.
_RESET_ANTWORT = {
    "erfolg": True,
    "hinweis": (
        "Falls ein Konto zu dieser Angabe existiert, haben wir eine E-Mail mit "
        "einem Link zum Zurücksetzen verschickt. Der Link ist "
        f"{RESET_GUELTIG_MINUTEN} Minuten gültig."
    ),
}


class PasswortVergessenReq(BaseModel):
    # Benutzername ODER E-Mail -- Leute merken sich mal das eine, mal das andere.
    kennung: str


class PasswortZuruecksetzenReq(BaseModel):
    token: str
    neues_passwort: str


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reset_mailtext(benutzername: str, link: str) -> tuple:
    text = (
        f"Hallo {benutzername},\n\n"
        "für dein Grana-Konto wurde das Zurücksetzen des Passworts angefordert.\n"
        "Über diesen Link vergibst du ein neues Passwort:\n\n"
        f"{link}\n\n"
        f"Der Link ist {RESET_GUELTIG_MINUTEN} Minuten gültig und funktioniert nur einmal.\n\n"
        "Warst du das nicht, kannst du diese Nachricht ignorieren -- dein "
        "Passwort bleibt dann unverändert.\n\n"
        "Grana"
    )
    html = (
        f"<p>Hallo {benutzername},</p>"
        "<p>für dein Grana-Konto wurde das Zurücksetzen des Passworts angefordert.</p>"
        f'<p><a href="{link}">Neues Passwort vergeben</a></p>'
        f"<p>Der Link ist {RESET_GUELTIG_MINUTEN} Minuten gültig und funktioniert nur einmal.</p>"
        "<p>Warst du das nicht, kannst du diese Nachricht ignorieren – dein "
        "Passwort bleibt dann unverändert.</p>"
        "<p>Grana</p>"
    )
    return text, html


@router.post(
    "/passwort/vergessen",
    summary="Zurücksetzen des Passworts anfordern",
    description="Verschickt einen Einmal-Link. Antwortet immer gleich, "
                "unabhängig davon, ob das Konto existiert.",
)
async def passwort_vergessen(req: PasswortVergessenReq, request: Request):
    from datetime import datetime, timedelta
    import secrets as _secrets
    from services.mailer import sende_mail, MailVersandFehler

    kennung = (req.kennung or "").strip()
    if not kennung:
        return _RESET_ANTWORT

    async with get_db_session() as session:
        treffer = await session.execute(
            text(
                "SELECT benutzername, email FROM nutzer "
                "WHERE lower(benutzername) = lower(:k) OR lower(email) = lower(:k)"
            ),
            {"k": kennung},
        )
        nutzer = treffer.mappings().first()

        # Kein Konto oder kein hinterlegtes Postfach: identische Antwort, keine
        # Mail. Der Aufrufer erfährt daraus nichts.
        if not nutzer or not (nutzer["email"] or "").strip():
            return _RESET_ANTWORT

        benutzername = nutzer["benutzername"]

        # Ältere, noch offene Anfragen entwerten -- es soll immer nur ein
        # gültiger Link im Umlauf sein.
        await session.execute(
            text(
                "UPDATE passwort_resets SET benutzt_am = :jetzt "
                "WHERE benutzername = :name AND benutzt_am IS NULL"
            ),
            {"jetzt": datetime.utcnow(), "name": benutzername},
        )

        roh_token = _secrets.token_urlsafe(32)
        await session.execute(
            text(
                "INSERT INTO passwort_resets (benutzername, token_hash, laeuft_ab, erstellt_am) "
                "VALUES (:name, :hash, :ablauf, :jetzt)"
            ),
            {
                "name": benutzername,
                "hash": _token_hash(roh_token),
                "ablauf": datetime.utcnow() + timedelta(minutes=RESET_GUELTIG_MINUTEN),
                "jetzt": datetime.utcnow(),
            },
        )

    link = f"{FRONTEND_URL.rstrip('/')}/passwort-neu?token={urllib.parse.quote(roh_token)}"
    text_teil, html_teil = _reset_mailtext(benutzername, link)
    try:
        await asyncio.to_thread(
            sende_mail, nutzer["email"], "Grana: Passwort zurücksetzen", text_teil, html_teil
        )
    except MailVersandFehler:
        # Auch hier keine abweichende Antwort -- sonst verrät der Fehlerfall,
        # dass es das Konto gibt. Im Log steht der Grund vollständig.
        logger.error("Passwort-Reset-Mail konnte nicht zugestellt werden.", exc_info=True)

    return _RESET_ANTWORT


@router.post(
    "/passwort/zuruecksetzen",
    summary="Neues Passwort mit Einmal-Token setzen",
)
async def passwort_zuruecksetzen(req: PasswortZuruecksetzenReq):
    from datetime import datetime

    neues = req.neues_passwort or ""
    if len(neues) < MIN_PASSWORT_LAENGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Das Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein.",
        )

    async with get_db_session() as session:
        # Gültigkeit in SQL prüfen, nicht in Python: SQLite liefert die
        # Zeitspalte als Zeichenkette zurück, PostgreSQL als datetime. Ein
        # Vergleich im Python-Code funktioniert deshalb nur auf einer der
        # beiden Datenbanken -- die Datenbank kennt ihre eigenen Typen.
        treffer = await session.execute(
            text(
                "SELECT id, benutzername FROM passwort_resets "
                "WHERE token_hash = :hash AND benutzt_am IS NULL AND laeuft_ab > :jetzt"
            ),
            {"hash": _token_hash((req.token or "").strip()), "jetzt": datetime.utcnow()},
        )
        eintrag = treffer.mappings().first()

        # Unbekannt, schon benutzt oder abgelaufen -- alles dieselbe Meldung.
        if not eintrag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dieser Link ist nicht mehr gültig. Fordere bitte einen neuen an.",
            )

        benutzername = eintrag["benutzername"]

        await session.execute(
            text("UPDATE nutzer SET passwort_hash = :hash WHERE benutzername = :name"),
            {"hash": bcrypt_hash(neues), "name": benutzername},
        )
        await session.execute(
            text("UPDATE passwort_resets SET benutzt_am = :jetzt WHERE id = :id"),
            {"jetzt": datetime.utcnow(), "id": eintrag["id"]},
        )
        # Wer das Passwort zurücksetzt, will in aller Regel auch bestehende
        # Sitzungen loswerden -- etwa weil jemand anderes Zugriff hatte.
        await session.execute(
            text("DELETE FROM sessions WHERE benutzername = :name"),
            {"name": benutzername},
        )

    logger.info("Passwort zurückgesetzt für %s", benutzername)
    return {
        "erfolg": True,
        "hinweis": "Dein Passwort wurde geändert. Du kannst dich jetzt anmelden.",
    }
