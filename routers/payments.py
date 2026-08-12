"""
routers/payments.py – Stripe-Zahlungsabwicklung & Premium-Abonnements

Endpoints:
    GET  /api/checkout/price          – Aktuellen Abo-Preis live von Stripe abfragen
    POST /api/checkout/create-session – Erstellt eine Stripe Checkout-Session (mit simulated Fallback)
    POST /api/checkout/webhook        – Stripe Webhook-Handler für Statusänderungen

Abhängigkeiten:
    - database        → get_db_session()
    - schemas.models  → CheckoutReq
"""

import asyncio
import logging
import os
import time
import urllib.parse
from typing import Optional

import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session
from services.cache import scryfall_cache
from schemas.models import CheckoutReq, VerifySessionReq

logger = logging.getLogger(__name__)

# ======================================================================
# Router-Instanz
# ======================================================================
router = APIRouter(
    prefix="/api",
    tags=["Zahlungen"],
)

# ======================================================================
# Hilfsfunktion für sichere Stripe Attribut-Auslesung
# ======================================================================
def get_stripe_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)

# Der Abo-Preis ändert sich vielleicht einmal im Jahr -- das Frontend fragt ihn
# aber bei jedem Seitenaufbau ab, und gleich aus zwei Komponenten (Preisseite und
# Upgrade-Dialog, der dauerhaft in der App hängt). Ohne Zwischenspeicher wurde
# daraus je Aufruf ein echter Stripe-Aufruf: im Log eines einzigen Besuchs über
# ein Dutzend. Bei mehreren tausend Nutzern wäre das ein Vielfaches der
# Stripe-Ratengrenze -- und jeder Aufruf verzögert den Seitenaufbau.
PREIS_CACHE_SEKUNDEN = int(os.getenv("PREMIUM_PRICE_CACHE_SECONDS", "600"))
_PREIS_CACHE_KEY = "checkout:preis:v1"


def _preis_cache_schluessel(price_id: str) -> str:
    # Die Preis-ID gehört in den Schlüssel: wird in der Konfiguration ein anderer
    # Preis hinterlegt, ist der alte Eintrag damit sofort gegenstandslos statt
    # noch zehn Minuten weiterzuleben.
    return f"{_PREIS_CACHE_KEY}:{price_id}"


def _preis_aus_cache(price_id: str):
    eintrag = scryfall_cache.get(_preis_cache_schluessel(price_id))
    if not isinstance(eintrag, dict):
        return None
    if time.time() - float(eintrag.get("zeit") or 0) >= PREIS_CACHE_SEKUNDEN:
        return None
    return eintrag.get("daten")


def _preis_merken(price_id: str, daten: dict) -> None:
    scryfall_cache.set(
        _preis_cache_schluessel(price_id), {"daten": daten, "zeit": time.time()}
    )


def _fallback_price():
    """Operator-konfigurierbarer Anzeige-Preis, falls Stripe (noch) nicht vollständig
    eingerichtet ist. Kein fest einprogrammierter Preis -- kommt aus der Umgebung
    (PREMIUM_PRICE_DISPLAY z.B. '3.90', PREMIUM_CURRENCY z.B. 'CHF'/'EUR'). So zeigt
    die Preisseite einen Preis statt 'nicht verfügbar', ohne dass ein Preis im Code
    hartcodiert wird."""
    raw = os.getenv("PREMIUM_PRICE_DISPLAY")
    if not raw:
        return None
    try:
        betrag = float(str(raw).replace(",", "."))
    except (ValueError, TypeError):
        return None
    return {
        "konfiguriert": True,
        "betrag": betrag,
        "waehrung": os.getenv("PREMIUM_CURRENCY", "CHF").upper(),
        "intervall": os.getenv("PREMIUM_INTERVAL", "month"),
        "quelle": "fallback",
    }


# ======================================================================
# GET /api/checkout/price – Aktuellen Preis live von Stripe abfragen
# ======================================================================
@router.get(
    "/checkout/price",
    summary="Aktuellen Abo-Preis abfragen",
)
async def get_checkout_price():
    """
    Liefert den tatsächlich in Stripe hinterlegten Preis (Betrag, Währung,
    Abrechnungsintervall) für STRIPE_PRICE_ID. Damit das Frontend nie einen
    veralteten, fest einprogrammierten Preis anzeigt -- ändert sich der Preis
    in Stripe, ändert sich automatisch auch die Anzeige, ohne Deploy.

    Ist Stripe nicht (vollständig) konfiguriert oder schlägt der Abruf fehl, wird
    -- falls gesetzt -- ein operator-konfigurierbarer Fallback-Preis aus der
    Umgebung (PREMIUM_PRICE_DISPLAY) zurückgegeben, damit die Preisseite nicht
    "Preis nicht verfügbar" anzeigt.
    """
    # Konfiguration ZUERST prüfen, dann erst den Zwischenspeicher: Fehlt der
    # Schlüssel oder die Preis-ID, darf kein zuvor gemerkter Preis mehr
    # ausgeliefert werden.
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not stripe_key or not price_id:
        return _fallback_price() or {"konfiguriert": False}

    gecacht = _preis_aus_cache(price_id)
    if gecacht is not None:
        return gecacht

    try:
        stripe.api_key = stripe_key
        # Der Aufruf geht über das Netz und blockiert sonst den Event-Loop für
        # alle anderen Anfragen.
        price = await asyncio.to_thread(stripe.Price.retrieve, price_id)
        betrag = (price.unit_amount or 0) / 100
        waehrung = (price.currency or "").upper()
        intervall = price.recurring.interval if price.recurring else "month"
        ergebnis = {
            "konfiguriert": True,
            "betrag": betrag,
            "waehrung": waehrung,
            "intervall": intervall,
        }
        # Nur Erfolge merken: eine Störung bei Stripe soll sich nicht für zehn
        # Minuten festsetzen.
        _preis_merken(price_id, ergebnis)
        return ergebnis
    except Exception as e:
        logger.exception("Error fetching Stripe price")
        return _fallback_price() or {"konfiguriert": False, "error": str(e)}

# ======================================================================
# POST /api/checkout/create-session – Checkout Session erstellen
# ======================================================================
@router.post(
    "/checkout/create-session",
    summary="Stripe Checkout Session erstellen",
)
async def create_checkout_session(req: CheckoutReq, current_user: str = Depends(get_current_user)):
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not stripe_key or not price_id:
        # Fallback simulated checkout url (Simuliert den Upgrade-Flow für lokale Entwicklung,
        # nur wenn Stripe wirklich nicht konfiguriert ist -- kein Dummy-Preis-Versuch mehr)
        mock_success_url = f"{req.host_url}/premium?status=success&mock_upgrade=true&user={urllib.parse.quote(current_user)}"
        return {"erfolg": True, "url": mock_success_url, "simulated": True}

    try:
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price': price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=req.host_url + "/premium?status=success&session_id={CHECKOUT_SESSION_ID}&user=" + urllib.parse.quote(current_user),
            cancel_url=req.host_url + "/premium?status=cancel",
            metadata={
                "benutzername": current_user
            }
        )
        return {"erfolg": True, "url": session.url, "simulated": False}
    except Exception as e:
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# POST /api/checkout/verify-session – Zahlung serverseitig bestätigen
# ======================================================================
@router.post(
    "/checkout/verify-session",
    summary="Abgeschlossene Checkout-Session serverseitig verifizieren",
)
async def verify_checkout_session(req: VerifySessionReq, current_user: str = Depends(get_current_user)):
    """
    Bestätigt eine zurückkehrende Checkout-Session direkt bei Stripe und schaltet
    Premium frei -- als robuster Fallback zum Webhook.

    Sicherheit: Die Session wird mit dem geheimen Stripe-Key SERVERSEITIG bei
    Stripe abgefragt (dem Client wird nichts geglaubt). Nur wenn die Zahlung
    tatsächlich erfolgt ist (payment_status == 'paid' bzw. status == 'complete')
    UND die Session zum eingeloggten Nutzer gehört (metadata.benutzername), wird
    die Rolle gesetzt. So kann niemand mit einer fremden/unbezahlten Session
    Premium erschleichen. Das ist idempotent zum Webhook (setzt denselben Zustand).
    """
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_key:
        return {"erfolg": False, "error": "Stripe ist auf diesem Server nicht konfiguriert."}

    try:
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.retrieve(req.session_id)
    except Exception as e:
        logger.exception("Fehler beim Abrufen der Checkout-Session %s", req.session_id)
        return {"erfolg": False, "error": f"Session konnte nicht geprüft werden: {e}"}

    payment_status = get_stripe_val(session, "payment_status")
    session_status = get_stripe_val(session, "status")
    metadata = get_stripe_val(session, "metadata", {}) or {}
    session_user = get_stripe_val(metadata, "benutzername")

    if session_user != current_user:
        # Session gehört nicht zum eingeloggten Nutzer -> niemals freischalten.
        return {"erfolg": False, "error": "Diese Zahlung gehört nicht zu deinem Konto."}

    if payment_status != "paid" and session_status != "complete":
        return {"erfolg": False, "bezahlt": False, "error": "Die Zahlung ist noch nicht abgeschlossen."}

    customer_id = get_stripe_val(session, "customer")
    subscription_id = get_stripe_val(session, "subscription")
    async with get_db_session() as session_db:
        await session_db.execute(
            text("UPDATE nutzer SET rolle='premium', stripe_customer_id = :cust_id, stripe_subscription_id = :sub_id WHERE benutzername = :name"),
            {"cust_id": customer_id, "sub_id": subscription_id, "name": current_user},
        )
    logger.info("User %s via verify-session auf Premium gesetzt (Session %s).", current_user, req.session_id)
    return {"erfolg": True, "rolle": "premium"}

# ======================================================================
# POST /api/checkout/cancel-subscription – Abo selbst kündigen (Self-Service)
# ======================================================================
@router.post(
    "/checkout/cancel-subscription",
    summary="Eigenes Premium-Abo kündigen",
)
async def cancel_subscription(current_user: str = Depends(get_current_user)):
    """
    Kündigt das Stripe-Abo des eingeloggten Nutzers zum Ende der bezahlten
    Periode (cancel_at_period_end) -- Self-Service, wie in den AGB zugesagt.

    Verhalten:
    - Premium bleibt bis zum Periodenende aktiv (der Nutzer hat dafür bezahlt);
      das Downgrade auf 'free' erledigt der bestehende
      customer.subscription.deleted-Webhook, wenn Stripe das Abo beendet.
    - Hat der Nutzer KEIN Stripe-Abo (z.B. per Admin/Dev-Upgrade Premium),
      gibt es eine ehrliche Fehlermeldung statt einer Schein-Kündigung.
    """
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe_key:
        return {"erfolg": False, "error": "Stripe ist auf diesem Server nicht konfiguriert."}

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT stripe_subscription_id FROM nutzer WHERE benutzername = :name"),
            {"name": current_user},
        )
        row = res.mappings().first()

    subscription_id = row["stripe_subscription_id"] if row else None
    if not subscription_id:
        return {
            "erfolg": False,
            "kein_abo": True,
            "error": "Für dieses Konto ist kein aktives Stripe-Abo hinterlegt.",
        }

    try:
        stripe.api_key = stripe_key
        sub = stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
    except Exception as e:
        logger.exception("Fehler beim Kündigen des Abos für %s", current_user)
        return {"erfolg": False, "error": f"Kündigung bei Stripe fehlgeschlagen: {e}"}

    # Periodenende ermitteln (neuere Stripe-API-Versionen liefern
    # current_period_end auf den Subscription-Items statt top-level).
    period_end = get_stripe_val(sub, "current_period_end")
    if not period_end:
        items = get_stripe_val(get_stripe_val(sub, "items", {}), "data", []) or []
        if items:
            period_end = get_stripe_val(items[0], "current_period_end")

    logger.info(
        "User %s hat Abo %s gekündigt (cancel_at_period_end, läuft bis %s).",
        current_user, subscription_id, period_end,
    )
    return {
        "erfolg": True,
        "laeuft_bis": period_end,  # Unix-Timestamp oder None
        "nachricht": "Dein Abo ist gekündigt. Premium bleibt bis zum Ende der bezahlten Periode aktiv.",
    }


# ======================================================================
# Gemeinsamer Webhook Event Processor
# ======================================================================
async def handle_stripe_webhook_logic(request: Request):
    """
    Verifiziert JEDE eingehende Webhook-Anfrage gegen die Stripe-Signatur --
    es gibt absichtlich keinen Bypass mehr (auch nicht über eine DEV_MODE-
    Env-Var), da ein falsch gesetztes Flag in Produktion sonst gefälschte
    Events (z.B. ein erfundenes "checkout.session.completed") akzeptieren
    und kostenloses Premium vergeben würde. Lokal/Dev-Tests laufen über
    echte, mit dem Stripe-Testsecret signierte Payloads (z.B. via
    `stripe listen` oder eine im Test erzeugte Signatur), nicht über
    unsignierte JSON-Bodies.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_key = os.getenv("STRIPE_SECRET_KEY")

    if stripe_key:
        stripe.api_key = stripe_key

    if not webhook_secret or not sig_header:
        raise HTTPException(status_code=400, detail="Missing webhook secret or stripe signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("GLOBALER FEHLER in Webhook construct")
        return JSONResponse(status_code=400, content={"error": str(e)})

    if event:
        event_type = get_stripe_val(event, "type")
        event_data = get_stripe_val(event, "data", {})
        event_obj = get_stripe_val(event_data, "object")
        
        if event_type == "checkout.session.completed":
            metadata = get_stripe_val(event_obj, "metadata", {})
            benutzername = get_stripe_val(metadata, "benutzername")
            customer_id = get_stripe_val(event_obj, "customer")
            subscription_id = get_stripe_val(event_obj, "subscription")
            if benutzername:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='premium', stripe_customer_id = :cust_id, stripe_subscription_id = :sub_id WHERE benutzername = :name"),
                        {"cust_id": customer_id, "sub_id": subscription_id, "name": benutzername}
                    )
                logger.info(
                    "User %s upgraded to premium via Stripe. Customer: %s, Subscription: %s.",
                    benutzername, customer_id, subscription_id,
                )
                return {"status": "success", "message": f"User {benutzername} upgraded to premium"}
                
        elif event_type == "customer.subscription.deleted":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free', stripe_subscription_id = NULL WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                logger.info("Downgraded user with Stripe Customer ID %s to free.", customer_id)
                return {"status": "success", "message": "User subscription cancelled"}
                
        elif event_type == "invoice.payment_failed":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free', stripe_subscription_id = NULL WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                logger.info("Downgraded user with Stripe Customer ID %s due to payment failure.", customer_id)
                return {"status": "success", "message": "User subscription suspended"}
            
    return {"status": "ignored"}

# ======================================================================
# POST /api/checkout/webhook – Stripe Webhook Event Handler (Legacy)
# ======================================================================
@router.post(
    "/checkout/webhook",
    summary="Stripe Webhook (Legacy)",
)
async def stripe_webhook(request: Request):
    return await handle_stripe_webhook_logic(request)

# ======================================================================
# POST /api/v1/payments/webhook – Neuer, offizieller Stripe Webhook Endpoint
# ======================================================================
@router.post(
    "/v1/payments/webhook",
    summary="Stripe Webhook (V1)",
)
async def stripe_webhook_v1(request: Request):
    return await handle_stripe_webhook_logic(request)

