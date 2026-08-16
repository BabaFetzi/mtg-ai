"""services/konto.py -- Auskunft über und Löschung von Nutzerdaten.

Zwei Pflichten aus der DSGVO, die es bisher gar nicht gab:

  * Artikel 20 (Datenübertragbarkeit): Wer fragt, bekommt seine Daten in einem
    gängigen, maschinenlesbaren Format. Der Sammlungs-CSV-Export deckte nur
    einen Teil ab -- Konto, Decks und Abo fehlten.
  * Artikel 17 (Löschung): Auf Verlangen muss alles weg.

Beides steht hier als Funktion, nicht im Endpunkt: so lässt es sich gegen eine
echte Datenbank prüfen, und beide Wege benutzen dieselbe Tabellenliste. Kommt
eine Tabelle dazu, fällt genau ein Test um, statt dass jahrelang unbemerkt
Reste zurückbleiben.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Alle Tabellen mit personenbezogenen Daten und die Spalte, in der der
# Benutzername steht. Diese Liste ist die einzige Stelle, an der das gepflegt
# wird -- Auskunft und Löschung lesen beide daraus.
NUTZER_TABELLEN = [
    ("sammlung_alben", "benutzername"),
    ("decks", "benutzername"),
    ("sessions", "benutzername"),
    ("passwort_resets", "benutzername"),
    ("ai_calls", "benutzername"),
    # Monatlicher KI-Verbrauch. Gehört zum Konto und sagt etwas über die
    # Nutzung aus -- also Auskunft UND Löschung.
    ("ki_nutzung", "benutzername"),
]

# Wird gelöscht, aber NICHT in die Auskunft aufgenommen.
#
# anmeldeversuche verknüpft einen Benutzernamen mit IP-Adressen. Das sind
# nicht zwingend die des Kontoinhabers: wer fremde Zugänge durchprobiert,
# hinterlässt hier SEINE Adresse unter dem angegriffenen Namen. Diese Zeilen
# dem Kontoinhaber auszuhändigen hiesse, Daten Dritter offenzulegen.
#
# Gelöscht werden müssen sie trotzdem: ohne das bliebe nach einer Löschung ein
# Benutzername mit IP-Adressen zurück. Von selbst verfallen sie ohnehin nach
# einer Stunde (services/anmeldeversuche.py).
TABELLEN_NUR_LOESCHEN = [
    ("anmeldeversuche", "benutzername"),
]

# Bewusst NICHT dabei: der Sperrvermerk gelöschter Konten. Er enthält nur den
# Benutzernamen und den Zeitpunkt und ist genau das, was die Löschung wirksam
# hält -- würde er mitgelöscht, wären die noch gültigen Token wieder brauchbar.
# Er verfällt von selbst, sobald keine Token mehr gültig sein können.
TABELLEN_OHNE_LOESCHUNG = {"geloeschte_konten"}

# Diese Felder gehören dem Nutzer und kommen in die Auskunft.
KONTO_FELDER = [
    "benutzername", "email", "rolle", "oauth_provider",
    "erstellt_am", "letzter_login", "stripe_customer_id", "stripe_subscription_id",
]

# Was NIE ausgeliefert wird: der Passwort-Hash (nützt nur einem Angreifer) und
# die Token-Hashes der Passwort-Zurücksetzungen. Beides sind Sicherheitsdaten,
# keine Auskunft über die Person.
GEHEIM = {"passwort_hash", "token_hash", "refresh_token"}


def _wert(v: Any) -> Any:
    """Datum zu ISO-Text, alles andere unverändert -- damit es JSON wird."""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)


def _zeile(row) -> Dict[str, Any]:
    return {k: _wert(v) for k, v in dict(row).items() if k not in GEHEIM}


async def sammle_nutzerdaten(session, benutzer: str) -> Dict[str, Any]:
    """Alles, was zu diesem Konto gespeichert ist -- als JSON-fähiges Dict."""
    daten: Dict[str, Any] = {
        "hinweis": (
            "Auskunft nach Artikel 15 und 20 DSGVO. Enthalten sind alle zu "
            "diesem Konto gespeicherten Daten. Nicht enthalten sind der "
            "Passwort-Hash und Sicherheits-Token -- sie sagen nichts über dich "
            "aus und wären in fremder Hand ein Risiko. Zahlungsdaten liegen bei "
            "Stripe und sind dort abrufbar."
        ),
        "konto": {},
    }

    res = await session.execute(
        text("SELECT * FROM nutzer WHERE benutzername = :name"), {"name": benutzer})
    konto = res.mappings().first()
    if konto:
        daten["konto"] = {k: _wert(v) for k, v in dict(konto).items()
                          if k in KONTO_FELDER}

    for tabelle, spalte in NUTZER_TABELLEN:
        try:
            res = await session.execute(
                text(f"SELECT * FROM {tabelle} WHERE {spalte} = :name"), {"name": benutzer})
            zeilen: List[Dict[str, Any]] = [_zeile(r) for r in res.mappings().all()]
        except Exception:
            # Eine fehlende Tabelle (ältere Installation) darf die Auskunft
            # nicht verhindern -- sie wird als leer ausgewiesen und protokolliert.
            logger.warning("Tabelle %s nicht lesbar", tabelle, exc_info=True)
            zeilen = []
        daten[tabelle] = zeilen

    return daten


async def loesche_nutzerdaten(session, benutzer: str) -> Dict[str, int]:
    """Löscht das Konto und alles, was daran hängt.

    Gibt je Tabelle die Zahl der gelöschten Zeilen zurück -- die Bestätigung
    soll sagen können, was tatsächlich passiert ist.
    """
    geloescht: Dict[str, int] = {}

    for tabelle, spalte in NUTZER_TABELLEN + TABELLEN_NUR_LOESCHEN:
        try:
            res = await session.execute(
                text(f"DELETE FROM {tabelle} WHERE {spalte} = :name"), {"name": benutzer})
            geloescht[tabelle] = res.rowcount or 0
        except Exception:
            logger.warning("Löschen in %s fehlgeschlagen", tabelle, exc_info=True)
            geloescht[tabelle] = 0

    res = await session.execute(
        text("DELETE FROM nutzer WHERE benutzername = :name"), {"name": benutzer})
    geloescht["nutzer"] = res.rowcount or 0

    return geloescht
