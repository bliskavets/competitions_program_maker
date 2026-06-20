"""E-mail sending. Defaults to a console backend that logs the message."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("sumo.email")


def send_email(to: str, subject: str, body: str) -> None:
    if settings.email_backend == "smtp" and settings.smtp_host:
        _send_smtp(to, subject, body)
    else:
        # Console backend — handy for local dev / tests. The code is printed
        # to the application log so the reset flow can be completed manually.
        log.info("EMAIL to=%s subject=%r\n%s", to, subject, body)
        print(f"[EMAIL] to={to} subject={subject}\n{body}", flush=True)


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


def send_reset_code(to: str, code: str) -> None:
    send_email(
        to,
        "Resetowanie hasła — System SUMO",
        "Otrzymaliśmy prośbę o zresetowanie hasła.\n\n"
        f"Twój kod weryfikacyjny: {code}\n\n"
        "Wprowadź ten kod w aplikacji, aby ustawić nowe hasło.\n"
        "Jeśli to nie Ty prosiłeś o zmianę hasła, zignoruj tę wiadomość.",
    )
