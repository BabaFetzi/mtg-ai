"""
schemas/models.py – Zentrale Pydantic Models für Request-Validierung

Alle Request- und Response-Schemas an einem Ort. Das eliminiert
doppelte BaseModel-Definitionen, die bisher über main.py verstreut waren.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ======================================================================
# AUTH
# ======================================================================
class LoginData(BaseModel):
    benutzername: str = Field(..., min_length=1, max_length=50)
    passwort: str = Field(..., min_length=1)


class RegisterData(BaseModel):
    benutzername: str = Field(..., min_length=1, max_length=50)
    passwort: str = Field(..., min_length=1)
    # E-Mail wird für die Registrierung erfasst (nötig für späteres
    # "Passwort vergessen"). Format wird im Endpunkt geprüft, damit keine
    # zusätzliche email-validator-Abhängigkeit nötig ist.
    email: str = Field(..., min_length=3, max_length=255)


class UpdateRoleReq(BaseModel):
    benutzername: str
    rolle: str = "free"


# ======================================================================
# SAMMLUNG (Collection)
# ======================================================================
class SammlungHinzufuegenReq(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str = "Standard"
    bild_url: Optional[str] = None
    preis: Optional[str] = None


class SammlungLoeschenReq(BaseModel):
    benutzername: str
    karten_name: str
    album_name: str = "Standard"


class AlbumLoeschenReq(BaseModel):
    benutzername: str
    album_name: str


# ======================================================================
# DECKS
# ======================================================================
class DeckErstellenReq(BaseModel):
    benutzername: str
    deck_name: str = Field(..., min_length=1, max_length=100)
    deck_liste: str = ""
    format: str = "commander"


class DeckUpdateReq(BaseModel):
    benutzername: Optional[str] = None
    deck_id: int
    deck_name: Optional[str] = None
    deck_liste: Optional[str] = None
    format: Optional[str] = None


class DeckLoeschenReq(BaseModel):
    benutzername: str
    deck_id: int


class DeckAnalyseReq(BaseModel):
    """Wird für /api/deck/visualize, /api/deck/stats, /api/deck/wert, /api/deck/analyse verwendet."""
    deck_liste: str
    benutzername: str = ""
    format: str = "commander"


class DeckCardReq(BaseModel):
    """Wird für /api/deck/add-card und /api/deck/remove-card verwendet."""
    benutzername: str
    deck_id: int
    card_name: str
    count: int = 1


class ValidateDeckReq(BaseModel):
    deck_liste: str
    format: str = "commander"


# ======================================================================
# KI / JUDGE
# ======================================================================
class JudgeReq(BaseModel):
    frage: str = Field(..., min_length=1)
    benutzername: str = ""


class ScanCombosReq(BaseModel):
    deck_liste: str
    benutzername: str = ""


# ======================================================================
# PAYMENTS
# ======================================================================
class CheckoutReq(BaseModel):
    benutzername: str
    host_url: str = "http://localhost:5173"


# ======================================================================
# KARTEN-SUCHE (Cards) – Response-Schemas für Dokumentation
# ======================================================================
class CardPrint(BaseModel):
    """Ein einzelner Druck einer Karte (Set + Bild + Preis)."""
    set_name: Optional[str] = None
    bild_url: str = ""
    preis: str = "0.00"


class CardSearchResult(BaseModel):
    """Antwort der Kartensuche /api/suche/{search_term}."""
    name: Optional[str] = None
    typ: Optional[str] = None
    text_de: str = ""
    prints: List[CardPrint] = []
    marktwert: str = "0.00"
    error: Optional[str] = None


class TrendingCard(BaseModel):
    """Einzelne Karte in der Trends-Antwort."""
    id: str
    name: str
    image_uris: Dict[str, str] = {}
    prices: Dict[str, Any] = {}
    set_name: Optional[str] = None
    album_name: Optional[str] = None


class TrendsResponse(BaseModel):
    """Antwort von /api/trends."""
    erfolg: bool = True
    personalized: bool = False
    data: List[TrendingCard] = []
