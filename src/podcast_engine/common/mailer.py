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
    """One email to send: recipient, subject and plain-text body."""

    to: str
    subject: str
    body: str


class Mailer(Protocol):
    """Sends email: password reset links and notices."""

    def send(self, email: Email) -> None:
        """Send one email.

        Args:
            email: The email to send.
        """
        ...


class SmtpMailer:
    """Sends email over SMTP.

    The compose stack sends to Mailpit, a local inbox (http://localhost:8025), so nothing leaves the
    machine. Set SMTP_HOST and the rest for a real mail service; its password belongs in Vault
    (``smtp_password``).
    """

    def __init__(self, settings: Settings) -> None:
        """Create the mailer.

        Args:
            settings: The SMTP host, port, sender, STARTTLS flag and credentials.
        """
        self._settings = settings

    def send(self, email: Email) -> None:
        """Send one email over SMTP, with STARTTLS and a login when configured.

        Only the subject is logged, never the recipient's address or the body, which may hold a
        reset link.

        Args:
            email: The email to send.
        """
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
        log.info("email_sent", subject=email.subject)


class NullMailer:
    """Used when no SMTP_HOST is set: logs that an email was not sent, never its content."""

    def send(self, email: Email) -> None:
        """Log that the email was not sent.

        Args:
            email: The email that would have been sent; only its subject is logged.
        """
        log.warning("email_not_sent", reason="SMTP_HOST is not set", subject=email.subject)


def make_mailer(settings: Settings) -> Mailer:
    """Return the mailer the settings call for.

    Args:
        settings: The app settings.

    Returns:
        An SMTP mailer when SMTP_HOST is set, else one that only logs.
    """
    return SmtpMailer(settings) if settings.smtp_host else NullMailer()
