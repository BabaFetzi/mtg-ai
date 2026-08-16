"""
routers/konto.py – Auskunft und Löschung des eigenen Kontos (DSGVO)

Endpoints:
    GET  /api/konto/export    – alle eigenen Daten als JSON-Datei
    POST /api/konto/loeschen  – Konto und alle Daten löschen

Beides verlangt eine Anmeldung; das Löschen zusätzlich das Passwort. Ein
versehentlicher Klick oder ein fremder Tab soll nicht die Sammlung eines
Jahres vernichten.
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from auth import get_current_user, konto_sofort_sperren, verify_passwort
from database import get_db_session
from services.konto import loesche_nutzerdaten, sammle_nutzerdaten
from services.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Konto"])


class KontoLoeschenReq(BaseModel):
    passwort: str
    # Bewusst getippte Bestätigung. Ein Knopf allein ist für einen Vorgang,
    # der nicht rückgängig zu machen ist, zu wenig.
    bestaetigung: str = ""


BESTAETIGUNGSWORT = "LÖSCHEN"


# ======================================================================
# GET /api/konto/export – Auskunft nach Artikel 15/20 DSGVO
# ======================================================================
@router.get(
    "/konto/export",
    summary="Alle eigenen Daten als JSON herunterladen",
)
async def konto_export(current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        daten = await sammle_nutzerdaten(session, current_user)

    inhalt = json.dumps(daten, ensure_ascii=False, indent=2)
    dateiname = f"grana-daten-{current_user}.json"
    return StreamingResponse(
        iter([inhalt.encode("utf-8")]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


# ======================================================================
# POST /api/konto/loeschen – Löschung nach Artikel 17 DSGVO
# ======================================================================
@router.post(
    "/konto/loeschen",
    summary="Konto und alle Daten unwiderruflich löschen",
)
@limiter.limit("5/hour")
async def konto_loeschen(req: KontoLoeschenReq, request: Request,
                          current_user: str = Depends(get_current_user)):
    if (req.bestaetigung or "").strip().upper() != BESTAETIGUNGSWORT:
        raise HTTPException(
            status_code=400,
            detail=f"Zum Löschen bitte '{BESTAETIGUNGSWORT}' eingeben.")

    async with get_db_session() as session:
        res = await session.execute(
            text("SELECT passwort_hash, stripe_subscription_id FROM nutzer "
                 "WHERE benutzername = :name"),
            {"name": current_user},
        )
        konto = res.mappings().first()

    if not konto:
        raise HTTPException(status_code=404, detail="Konto nicht gefunden.")

    # Erneute Passwortprüfung: ein gestohlenes Zugriffstoken allein soll nicht
    # reichen, um eine Sammlung zu vernichten.
    if not konto["passwort_hash"] or not verify_passwort(req.passwort, konto["passwort_hash"]):
        raise HTTPException(status_code=403, detail="Passwort stimmt nicht.")

    # Laufendes Abo bei Stripe beenden. Fehlschläge dürfen die Löschung NICHT
    # verhindern -- das Recht auf Löschung hängt nicht daran, ob ein fremder
    # Dienst gerade erreichbar ist. Sie werden protokolliert, damit das Abo von
    # Hand beendet werden kann.
    abo = (konto["stripe_subscription_id"] or "").strip()
    abo_beendet = False
    if abo:
        try:
            import stripe
            stripe.Subscription.delete(abo)
            abo_beendet = True
            logger.info("Abo %s bei Kontolöschung von %s beendet", abo, current_user)
        except Exception:
            logger.exception(
                "Abo %s konnte bei der Löschung von %s nicht beendet werden -- "
                "bitte im Stripe-Dashboard prüfen.", abo, current_user)

    async with get_db_session() as session:
        geloescht = await loesche_nutzerdaten(session, current_user)
        # Sperrvermerk, damit die noch gültigen Token nicht weiterlaufen. Der
        # Auffrischungs-Token gilt 30 Tage -- ohne diesen Eintrag könnte sich
        # das gelöschte Konto einen Monat lang neue Zugriffstoken holen.
        await session.execute(
            text("INSERT INTO geloeschte_konten (benutzername, geloescht_am) "
                 "VALUES (:name, :zeit)"),
            {"name": current_user, "zeit": datetime.utcnow()},
        )
    konto_sofort_sperren(current_user)

    logger.info("Konto %s gelöscht: %s", current_user, geloescht)
    return {
        "erfolg": True,
        "geloescht": geloescht,
        "abo_beendet": abo_beendet,
        "abo_hinweis": (
            "Dein Abo wurde beendet." if abo_beendet
            else ("Dein Abo konnte nicht automatisch beendet werden. Bitte melde "
                  "dich bei uns, damit wir das von Hand erledigen."
                  if abo else "")
        ),
    }
