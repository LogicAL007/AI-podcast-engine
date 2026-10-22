"""Sending email (password reset links and notices) over SMTP.

The compose stack sends to Mailpit, a local inbox (http://localhost:8025), so nothing leaves the
machine. Set SMTP_HOST and the rest for a real mail service; its password belongs in Vault
(``smtp_password``). With no SMTP_HOST, email is not sent and only the fact is logged, never the
message, which may hold a reset link.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from podcast_engine.common.config import Settings
from podcast_engine.common.logging import get_logger

log = get_logger("mailer")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, email: Email) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, email: Email) -> None:
        s = self._settings
        message = EmailMessage()
        message["From"] = s.mail_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(message)
        log.info("email_sent", subject=email.subject)  # not the recipient's address or the body


class NullMailer:
    def send(self, email: Email) -> None:
        log.warning("email_not_sent", reason="SMTP_HOST is not set", subject=email.subject)


def make_mailer(settings: Settings) -> Mailer:
    return SmtpMailer(settings) if settings.smtp_host else NullMailer()
