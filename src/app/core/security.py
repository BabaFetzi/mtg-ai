from fastapi import Depends, HTTPException, status
from sqlalchemy import text

from auth import get_current_user
from database import get_db_session, check_user_premium

async def require_premium(username: str = Depends(get_current_user)) -> str:
    """
    Harte Paywall: Blockiert den Zugriff auf Premium-Features für Free-User.
    Gibt HTTP 403 Forbidden zurück, wenn der User kein Premium-Mitglied ist.
    """
    is_premium = await check_user_premium(username)
    if not is_premium:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieses Premium-Feature steht nur Premium-Mitgliedern zur Verfügung."
        )
    return username

async def check_deck_limit(username: str = Depends(get_current_user)) -> str:
    """
    Weiche Paywall: Prüft, ob ein Free-User sein Deck-Limit (max. 1 Deck) erreicht hat.
    Gibt HTTP 403 Forbidden zurück, wenn das Limit überschritten wird.
    """
    is_premium = await check_user_premium(username)
    if not is_premium:
        async with get_db_session() as session:
            res = await session.execute(
                text("SELECT COUNT(*) as count FROM decks WHERE benutzername = :name"),
                {"name": username}
            )
            row = res.mappings().first()
            if row and row["count"] >= 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Free-Mitglieder können maximal 1 Deck erstellen. Bitte upgrade auf Premium für unbegrenzte Decks!"
                )
    return username
