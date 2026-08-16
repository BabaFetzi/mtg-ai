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
from datetime import datetime, timezone
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

# ======================================================================
# Welche Abo-Zustände Premium bedeuten
# ======================================================================
# Stripe kennt sieben Zustände. Entscheidend ist "past_due": die Zahlung ist
# offen, Stripe versucht es aber noch tagelang erneut, und meistens klappt es.
# Wer in dieser Zeit ausgesperrt wird, verliert seinen Zugang, obwohl er zahlt
# -- genau das ist vorher passiert, weil schon der erste Fehlversuch
# herabstufte.
#
#   active, trialing  -> bezahlt bzw. Testphase          -> Premium
#   past_due          -> Zahlung offen, Stripe probiert  -> Premium (Karenz)
#   unpaid            -> Wiederholungen erschöpft        -> free
#   canceled          -> beendet                         -> free
#   incomplete        -> erste Zahlung nie abgeschlossen -> free
#   incomplete_expired-> Frist dafür abgelaufen          -> free
PREMIUM_STATUS = frozenset({"active", "trialing", "past_due"})
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
        event_id = get_stripe_val(event, "id")
        event_created = get_stripe_val(event, "created")
        kunde_im_ereignis = get_stripe_val(event_obj, "customer")

        # Wiederholung und Reihenfolge pruefen, BEVOR irgendetwas geaendert
        # wird. Siehe database.StripeEreignis.
        if event_id:
            if await _schon_verarbeitet(event_id):
                logger.info("Stripe-Ereignis %s war schon da -- übersprungen.", event_id)
                return {"status": "duplicate", "message": "event already processed"}
            if event_type in ABO_EREIGNISSE and await _veraltet(
                    kunde_im_ereignis, event_created):
                logger.warning(
                    "Stripe-Ereignis %s (%s) ist älter als ein bereits "
                    "verarbeitetes -- ignoriert.", event_id, event_type)
                await _ereignis_merken(event_id, event_type, kunde_im_ereignis,
                                       event_created)
                return {"status": "stale", "message": "older than processed event"}

        # Erst verarbeiten, dann merken. Bricht die Verarbeitung ab, wird das
        # Ereignis NICHT als erledigt vermerkt und Stripe darf es erneut
        # zustellen. Das setzt voraus, dass die Handler unten Zustaende SETZEN
        # und nichts hochzaehlen -- wer hier etwas Zaehlendes ergaenzt, muss
        # das Merken in dieselbe Transaktion holen.
        antwort = await _ereignis_verarbeiten(event_type, event_obj)
        if event_id:
            await _ereignis_merken(event_id, event_type, kunde_im_ereignis,
                                   event_created)
        return antwort

    return {"status": "ignored"}


# Nur fuer diese Ereignisse ist die Reihenfolge entscheidend -- sie beschreiben
# alle denselben Abo-Zustand und wuerden sich sonst gegenseitig ueberschreiben.
ABO_EREIGNISSE = frozenset({
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
})


async def _schon_verarbeitet(event_id: str) -> bool:
    try:
        async with get_db_session() as session_db:
            res = await session_db.execute(
                text("SELECT 1 FROM stripe_ereignisse WHERE id = :id"),
                {"id": event_id})
            return res.scalar_one_or_none() is not None
    except Exception:
        # Lieber einmal zu viel verarbeiten als ein Ereignis verlieren: die
        # Handler setzen Zustaende und vertragen eine Wiederholung.
        logger.warning("Ereignis-Wiederholung nicht prüfbar", exc_info=True)
        return False


async def _veraltet(kunde: Optional[str], erstellt: Optional[int]) -> bool:
    """Gibt es für diesen Kunden schon ein NEUERES Abo-Ereignis?"""
    if not kunde or not erstellt:
        return False
    platzhalter = {f"t{i}": t for i, t in enumerate(sorted(ABO_EREIGNISSE))}
    inliste = ", ".join(f":{name}" for name in platzhalter)
    try:
        async with get_db_session() as session_db:
            res = await session_db.execute(
                text(f"SELECT MAX(erstellt) FROM stripe_ereignisse "
                     f"WHERE kunde = :kunde AND typ IN ({inliste})"),
                {"kunde": kunde, **platzhalter})
            neuestes = res.scalar_one_or_none()
        return neuestes is not None and int(neuestes) > int(erstellt)
    except Exception:
        logger.warning("Reihenfolge der Stripe-Ereignisse nicht prüfbar", exc_info=True)
        return False


async def _ereignis_merken(event_id: str, typ: Optional[str],
                           kunde: Optional[str], erstellt: Optional[int]) -> None:
    try:
        async with get_db_session() as session_db:
            await session_db.execute(
                text("INSERT INTO stripe_ereignisse (id, typ, kunde, erstellt, "
                     "verarbeitet_am) VALUES (:id, :typ, :kunde, :erstellt, :jetzt) "
                     "ON CONFLICT (id) DO NOTHING"),
                {"id": event_id, "typ": typ, "kunde": kunde,
                 "erstellt": erstellt, "jetzt": datetime.now(timezone.utc)})
    except Exception:
        logger.warning("Stripe-Ereignis %s nicht vermerkbar", event_id, exc_info=True)


async def _ereignis_verarbeiten(event_type: Optional[str], event_obj):
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
            await _rolle_setzen(customer_id, "free", abo_behalten=False)
            logger.info("Abo von Kunde %s beendet -- zurück auf free.", customer_id)
            return {"status": "success", "message": "User subscription cancelled"}

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        # DIE massgebliche Quelle für den Abo-Zustand. Stripe schickt das
        # bei jedem Statuswechsel -- auch, wenn eine zunächst
        # fehlgeschlagene Zahlung im zweiten Anlauf doch klappt. Ohne
        # dieses Ereignis kam ein Nutzer nach einem Zahlungsproblem NIE
        # wieder auf Premium zurück.
        customer_id = get_stripe_val(event_obj, "customer")
        status = (get_stripe_val(event_obj, "status") or "").lower()
        subscription_id = get_stripe_val(event_obj, "id")
        if customer_id and status:
            rolle = "premium" if status in PREMIUM_STATUS else "free"
            await _rolle_setzen(customer_id, rolle,
                                abo_behalten=(rolle == "premium"),
                                subscription_id=subscription_id)
            logger.info("Abo von Kunde %s hat Status %s -> Rolle %s.",
                        customer_id, status, rolle)
            return {"status": "success", "message": f"subscription {status} -> {rolle}"}

    elif event_type == "invoice.payment_failed":
        # KEIN sofortiges Herabstufen mehr.
        #
        # Vorher setzte schon der erste Fehlversuch die Rolle auf 'free'.
        # Stripe versucht danach aber noch tagelang erneut (Dunning), und
        # meistens geht die Zahlung durch -- eine kurz abgelaufene Karte
        # kostete den Kunden also sofort seinen Zugang, obwohl er weiter
        # zahlt. Zurueck kam er nie, weil das Gegenereignis nicht
        # verarbeitet wurde.
        #
        # Das Herabstufen erledigen jetzt die Abo-Ereignisse: bei
        # erschöpften Wiederholungen meldet Stripe den Statuswechsel
        # (unpaid/canceled) oder loescht das Abo.
        customer_id = get_stripe_val(event_obj, "customer")
        logger.warning(
            "Zahlung von Kunde %s fehlgeschlagen. Premium bleibt vorerst "
            "bestehen -- Stripe versucht es erneut.", customer_id)
        return {"status": "success", "message": "payment failure noted, access kept"}

    return {"status": "ignored"}


async def _rolle_setzen(customer_id: str, rolle: str, abo_behalten: bool,
                        subscription_id: Optional[str] = None) -> None:
    """Setzt die Rolle anhand der Stripe-Kundennummer.

    `abo_behalten=False` leert zusätzlich stripe_subscription_id -- das Abo
    existiert dann nicht mehr. Bei einer blossen Herabstufung (Status
    unpaid/canceled) bleibt die Nummer stehen, damit ein spaeteres
    Wiederaufleben demselben Abo zugeordnet werden kann.
    """
    if subscription_id and abo_behalten:
        sql = ("UPDATE nutzer SET rolle = :rolle, stripe_subscription_id = :sub "
               "WHERE stripe_customer_id = :cust")
        params = {"rolle": rolle, "sub": subscription_id, "cust": customer_id}
    elif abo_behalten:
        sql = "UPDATE nutzer SET rolle = :rolle WHERE stripe_customer_id = :cust"
        params = {"rolle": rolle, "cust": customer_id}
    else:
        sql = ("UPDATE nutzer SET rolle = :rolle, stripe_subscription_id = NULL "
               "WHERE stripe_customer_id = :cust")
        params = {"rolle": rolle, "cust": customer_id}

    async with get_db_session() as session_db:
        await session_db.execute(text(sql), params)

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

