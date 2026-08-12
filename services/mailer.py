"""
services/mailer.py – E-Mail-Versand über SMTP

Bewusst SMTP statt einer Anbieter-Bibliothek: Postmark, Resend, Brevo, Mailgun
und jeder eigene Server sprechen SMTP. Ein Anbieterwechsel ist damit eine
Änderung in der .env und kein Codeumbau.

Verhalten ohne Konfiguration:
- Entwicklung: Die Mail wird ins Log geschrieben. Der Rücksetz-Link steht damit
  im Terminal, sodass man den Ablauf lokal komplett durchspielen kann, ohne
  einen Mailanbieter einzurichten.
- Produktion: Der Versand schlägt hörbar fehl (Exception), statt eine Mail
  stillschweigend zu verschlucken. Eine nicht angekommene Passwort-Mail ist
  sonst ein Fehler, den erst der Kunde meldet.
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORT = os.getenv("SMTP_PASSWORD", "")
SMTP_ABSENDER = os.getenv("SMTP_FROM", "").strip()
# STARTTLS (Port 587) ist der Normalfall; implizites TLS (Port 465) über
# SMTP_TLS_MODUS=ssl.
SMTP_TLS_MODUS = os.getenv("SMTP_TLS_MODE", "starttls").strip().lower()

SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))


class MailVersandFehler(RuntimeError):
    """Der Versand ist fehlgeschlagen und die Mail kam NICHT an."""


def mailversand_konfiguriert() -> bool:
    return bool(SMTP_HOST and SMTP_ABSENDER)


def _ist_produktion() -> bool:
    # Erst zur Laufzeit lesen, damit Tests die Umgebung umstellen können.
    return os.getenv("GRANA_ENV", "development").strip().lower() in {
        "production", "prod", "produktion"
    }


def sende_mail(empfaenger: str, betreff: str, text: str, html: Optional[str] = None) -> None:
    """Verschickt eine Mail. Wirft MailVersandFehler, wenn sie nicht rausging.

    Args:
        empfaenger: Ziel-Adresse.
        betreff: Betreffzeile.
        text: Nur-Text-Fassung (Pflicht -- manche Klienten zeigen nur diese).
        html: Optionale HTML-Fassung.
    """
    if not empfaenger or "@" not in empfaenger:
        raise MailVersandFehler(f"Ungültige Empfängeradresse: {empfaenger!r}")

    if not mailversand_konfiguriert():
        if _ist_produktion():
            raise MailVersandFehler(
                "SMTP ist nicht konfiguriert (SMTP_HOST und SMTP_FROM fehlen). "
                "In der Produktion darf eine Mail nicht stillschweigend "
                "verlorengehen."
            )
        # Entwicklung: sichtbar machen statt verschlucken.
        logger.warning(
            "Kein SMTP konfiguriert – Mail wird nur protokolliert.\n"
            "  An:      %s\n  Betreff: %s\n%s",
            empfaenger, betreff, text,
        )
        return

    nachricht = EmailMessage()
    nachricht["From"] = SMTP_ABSENDER
    nachricht["To"] = empfaenger
    nachricht["Subject"] = betreff
    nachricht.set_content(text)
    if html:
        nachricht.add_alternative(html, subtype="html")

    kontext = ssl.create_default_context()
    try:
        if SMTP_TLS_MODUS == "ssl":
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=kontext) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORT)
                server.send_message(nachricht)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
                if SMTP_TLS_MODUS != "none":
                    server.starttls(context=kontext)
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORT)
                server.send_message(nachricht)
    except Exception as fehler:
        # Die Adresse gehört ins Log, der Inhalt nicht.
        logger.error("Mailversand an %s fehlgeschlagen: %s", empfaenger, fehler)
        raise MailVersandFehler(str(fehler)) from fehler

    logger.info("Mail versendet an %s (%s)", empfaenger, betreff)
