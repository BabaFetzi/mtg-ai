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

import logging
import os
import urllib.parse
from typing import Optional

import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session
from schemas.models import CheckoutReq

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
    """
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not stripe_key or not price_id:
        return {"konfiguriert": False}

    try:
        stripe.api_key = stripe_key
        price = stripe.Price.retrieve(price_id)
        betrag = (price.unit_amount or 0) / 100
        waehrung = (price.currency or "").upper()
        intervall = price.recurring.interval if price.recurring else "month"
        return {
            "konfiguriert": True,
            "betrag": betrag,
            "waehrung": waehrung,
            "intervall": intervall,
        }
    except Exception as e:
        logger.exception("Error fetching Stripe price")
        return {"konfiguriert": False, "error": str(e)}

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

