"""services/fehlermeldung.py -- Fehler melden, statt sie zu übersehen.

Ohne Überwachung merkt man einen Ausfall erst, wenn sich jemand beschwert --
und bei einem Bezahlprodukt beschwert sich der zweite Kunde nicht mehr, der
kündigt. Diese Anbindung schickt unbehandelte Fehler an Sentry, sobald ein DSN
gesetzt ist.

Bewusst so gebaut:
  * Ohne SENTRY_DSN passiert gar nichts. Die App muss auch ohne
    Überwachungsdienst laufen -- lokal, in Tests, bei einem Ausfall von Sentry.
  * Fehlt das Paket, gibt es eine Warnung und keinen Absturz. Ein
    Überwachungswerkzeug, das den Start verhindert, wäre die schlechteste
    aller Möglichkeiten.
  * Personenbezogene Daten werden NICHT mitgeschickt (send_default_pii=False),
    und Zugangsdaten werden vor dem Senden entfernt. Ein Fehlerbericht darf
    nicht zum Datenleck werden.

Was diese Säuberung NICHT leisten kann: Sentry schickt zu jedem Rahmen auch die
umliegenden Quelltextzeilen mit. Steht ein Geheimnis fest im Code, geht es damit
mit -- dagegen hilft nur, keine Geheimnisse in den Quelltext zu schreiben. Die
Werte von Variablen und Kopfzeilen sind abgedeckt.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from services import umgebung

logger = logging.getLogger(__name__)

# Felder, die niemals in einem Fehlerbericht landen dürfen -- auch nicht
# versehentlich über Kopfzeilen oder lokale Variablen.
GEHEIME_FELDER = {
    "authorization", "cookie", "set-cookie", "x-api-key",
    "passwort", "password", "passwort_hash", "token", "access_token",
    "refresh_token", "refresh-token", "jwt_secret_key", "stripe_secret_key",
    "stripe_webhook_secret", "gemini_api_key", "smtp_password",
}

ERSATZ = "[entfernt]"


# Sentry legt lokale Variablen tief verschachtelt ab:
#   event -> exception -> values[] -> stacktrace -> frames[] -> vars -> passwort
# Das sind allein sieben Ebenen. Eine zu knappe Grenze sieht harmlos aus, lässt
# aber genau die Stelle ungesäubert, an der die Geheimnisse stehen -- geprüft an
# einem echten Sentry-Ereignis, bei dem "hunter2" mit Grenze 6 durchkam.
MAX_TIEFE = 25


def _saeubern(daten: Any, tiefe: int = 0) -> Any:
    """Ersetzt alles, was nach Zugangsdaten aussieht."""
    if tiefe > MAX_TIEFE or daten is None:
        return daten
    if isinstance(daten, dict):
        sauber = {}
        for schluessel, wert in daten.items():
            if str(schluessel).lower() in GEHEIME_FELDER:
                sauber[schluessel] = ERSATZ
            else:
                sauber[schluessel] = _saeubern(wert, tiefe + 1)
        return sauber
    if isinstance(daten, list):
        return [_saeubern(w, tiefe + 1) for w in daten]
    return daten


def vor_dem_senden(ereignis: Dict[str, Any], hinweis: Optional[Dict] = None) -> Dict[str, Any]:
    """Wird von Sentry vor jedem Versand aufgerufen."""
    try:
        return _saeubern(ereignis)
    except Exception:  # pragma: no cover -- darf den Versand nie sprengen
        logger.debug("Fehlerbericht nicht säuberbar", exc_info=True)
        return ereignis


def einrichten() -> bool:
    """Startet die Fehlermeldung, wenn ein DSN gesetzt ist.

    Gibt zurück, ob die Überwachung aktiv ist.
    """
    dsn = umgebung.text("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN nicht gesetzt -- Fehler werden nur ins Log geschrieben.")
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "SENTRY_DSN ist gesetzt, aber das Paket sentry-sdk fehlt. "
            "Installiere es mit 'pip install sentry-sdk' -- bis dahin werden "
            "Fehler nur ins Log geschrieben.")
        return False

    betriebsart = umgebung.text("GRANA_ENV", "development")
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=betriebsart,
            # Anteil der Anfragen, für die Laufzeiten gemessen werden. 0 heisst:
            # nur Fehler. Messungen kosten Geld und Rechenzeit; wer sie will,
            # stellt sie bewusst ein.
            traces_sample_rate=umgebung.zahl("SENTRY_TRACES_SAMPLE_RATE", 0.0),
            # Keine personenbezogenen Daten (IP-Adressen, Kopfzeilen, Rumpf).
            send_default_pii=False,
            before_send=vor_dem_senden,
            release=umgebung.roh("GRANA_VERSION"),
        )
    except Exception:
        logger.warning("Sentry liess sich nicht einrichten", exc_info=True)
        return False

    logger.info("Fehlermeldung aktiv (Umgebung: %s)", betriebsart)
    return True
