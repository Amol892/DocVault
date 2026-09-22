"""Outgoing email, behind one small interface so the rest of the code never touches SMTP.

Every email is sent as `multipart/alternative`: a plain-text part first (what a client shows if
it can't or won't render HTML) and an HTML part second, built from app/templates/emails/ (see
services/email_templates.py). Without SMTP_HOST the message is written to the log instead
(development). A failed send never fails the request that triggered it: callers use
`send_quietly`, which reports whether the message went out.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str  # plain-text fallback
    html: str  # rendered HTML body


class Mailer(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class LogMailer:
    """Development fallback: nothing is sent, the plain-text body (links included) is logged."""

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "EMAIL (SMTP_HOST is not set, so nothing was sent)\nTo: %s\nSubject: %s\n\n%s",
            message.to,
            message.subject,
            message.body,
        )


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        starttls: bool,
        use_ssl: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._starttls = starttls
        self._use_ssl = use_ssl

    def _deliver(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)  # plain-text part
        mime.add_alternative(message.html, subtype="html")  # HTML part, preferred by clients
        context = ssl.create_default_context()
        if self._use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                self._host, self._port, timeout=15, context=context
            )
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=15)
        with server:
            if self._starttls and not self._use_ssl:
                server.starttls(context=context)
            if self._username:
                server.login(self._username, self._password or "")
            server.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        # smtplib is blocking: keep it off the event loop
        await asyncio.to_thread(self._deliver, message)


@lru_cache
def _mailer() -> Mailer:
    settings = get_settings()
    if not settings.smtp_host:
        return LogMailer()
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        sender=settings.smtp_from,
        starttls=settings.smtp_starttls,
        use_ssl=settings.smtp_ssl,
    )


def get_mailer() -> Mailer:
    """FastAPI dependency: the configured mailer (tests override it)."""
    return _mailer()


async def send_quietly(mailer: Mailer, message: EmailMessage) -> bool:
    """Send, and report whether it worked. Failures are logged without the message body (it
    may hold a link that is a credential)."""
    try:
        await mailer.send(message)
    except Exception:
        logger.exception("could not send email to %s (subject: %s)", message.to, message.subject)
        return False
    return True
