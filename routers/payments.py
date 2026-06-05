"""
routers/payments.py – Stripe-Zahlungsabwicklung & Premium-Abonnements

Endpoints:
    POST /api/checkout/create-session – Erstellt eine Stripe Checkout-Session (mit simulated Fallback)
    POST /api/checkout/webhook        – Stripe Webhook-Handler für Statusänderungen

Abhängigkeiten:
    - database        → get_db_session()
    - schemas.models  → CheckoutReq
"""

import json
import os
import urllib.parse
from typing import Optional

import stripe
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import get_db_session
from schemas.models import CheckoutReq

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
# POST /api/checkout/create-session – Checkout Session erstellen
# ======================================================================
@router.post(
    "/checkout/create-session",
    summary="Stripe Checkout Session erstellen",
)
async def create_checkout_session(req: CheckoutReq):
    if not req.benutzername:
        return {"erfolg": False, "error": "Benutzername erforderlich"}
    
    stripe_key = os.getenv("STRIPE_API_KEY")
    if not stripe_key:
        # Fallback simulated checkout url (Simuliert den Upgrade-Flow für lokale Entwicklung)
        mock_success_url = f"{req.host_url}/premium?status=success&mock_upgrade=true&user={urllib.parse.quote(req.benutzername)}"
        return {"erfolg": True, "url": mock_success_url, "simulated": True}
        
    try:
        stripe.api_key = stripe_key
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price': os.getenv("STRIPE_PRICE_ID", "price_dummy_123"),
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=req.host_url + "/premium?status=success&session_id={CHECKOUT_SESSION_ID}&user=" + urllib.parse.quote(req.benutzername),
            cancel_url=req.host_url + "/premium?status=cancel",
            metadata={
                "benutzername": req.benutzername
            }
        )
        return {"erfolg": True, "url": session.url, "simulated": False}
    except Exception as e:
        return {"erfolg": False, "error": str(e)}

# ======================================================================
# Gemeinsamer Webhook Event Processor
# ======================================================================
async def handle_stripe_webhook_logic(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_key = os.getenv("STRIPE_API_KEY")
    
    if stripe_key:
        stripe.api_key = stripe_key
        
    event = None
    try:
        if os.getenv("DEV_MODE") == "True":
            if webhook_secret and sig_header:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            else:
                data = json.loads(payload)
                event = stripe.Event.construct_from(data, stripe.api_key)
        else:
            if not webhook_secret or not sig_header:
                raise HTTPException(status_code=400, detail="Missing webhook secret or stripe signature header in production mode")
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"GLOBALER FEHLER in Webhook construct: {e}")
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
                print(f"User {benutzername} upgraded to premium via Stripe. Customer: {customer_id}, Subscription: {subscription_id}.")
                return {"status": "success", "message": f"User {benutzername} upgraded to premium"}
                
        elif event_type == "customer.subscription.deleted":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free', stripe_subscription_id = NULL WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                print(f"Downgraded user with Stripe Customer ID {customer_id} to free.")
                return {"status": "success", "message": "User subscription cancelled"}
                
        elif event_type == "invoice.payment_failed":
            customer_id = get_stripe_val(event_obj, "customer")
            if customer_id:
                async with get_db_session() as session_db:
                    await session_db.execute(
                        text("UPDATE nutzer SET rolle='free', stripe_subscription_id = NULL WHERE stripe_customer_id = :cust_id"),
                        {"cust_id": customer_id}
                    )
                print(f"Downgraded user with Stripe Customer ID {customer_id} due to payment failure.")
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

