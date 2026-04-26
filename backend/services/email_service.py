"""
Pluggable email sender.

Backends:
 - ConsoleEmailBackend (default): prints the message to stdout. Safe for local
   dev — your candidates won't receive anything.
 - SMTPEmailBackend: standard smtplib over STARTTLS or SSL. Use Gmail app
   password, SendGrid, Mailgun, SES, etc.

Select via env var EMAIL_BACKEND=console|smtp (defaults to console).

SMTP config:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_USE_TLS (default true), SMTP_USE_SSL (default false)
    EMAIL_FROM (e.g. "Interveux Hiring <noreply@example.com>")
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional, Protocol

log = logging.getLogger("interveux.email")


class EmailBackend(Protocol):
    name: str

    def send(self, *, to: str, subject: str, text: str, html: Optional[str] = None) -> None: ...


class ConsoleEmailBackend:
    """Prints emails to the log. Useful for dev without SMTP creds configured."""

    name = "console"

    def send(self, *, to: str, subject: str, text: str, html: Optional[str] = None) -> None:
        banner = "=" * 72
        log.warning(
            "\n%s\n[CONSOLE EMAIL] to=%s\nsubject=%s\n%s\n%s\n%s\n",
            banner, to, subject, "-" * 72, text.strip(), banner,
        )


class SMTPEmailBackend:
    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: Optional[str],
        password: Optional[str],
        use_tls: bool,
        use_ssl: bool,
        sender: str,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.sender = sender

    def send(self, *, to: str, subject: str, text: str, html: Optional[str] = None) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        if self.use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=20) as s:
                if self.user:
                    s.login(self.user, self.password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                s.ehlo()
                if self.use_tls:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if self.user:
                    s.login(self.user, self.password or "")
                s.send_message(msg)


def _get_bool(env: str, default: bool) -> bool:
    val = os.getenv(env)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def build_backend_from_env() -> EmailBackend:
    choice = (os.getenv("EMAIL_BACKEND") or "console").strip().lower()
    if choice == "smtp":
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER") or None
        password = os.getenv("SMTP_PASSWORD") or None
        sender = os.getenv("EMAIL_FROM") or (user or "noreply@localhost")
        use_tls = _get_bool("SMTP_USE_TLS", True)
        use_ssl = _get_bool("SMTP_USE_SSL", False)
        if not host:
            log.warning("EMAIL_BACKEND=smtp but SMTP_HOST is empty; falling back to console.")
            return ConsoleEmailBackend()
        return SMTPEmailBackend(
            host=host, port=port, user=user, password=password,
            use_tls=use_tls, use_ssl=use_ssl, sender=sender,
        )
    return ConsoleEmailBackend()


_backend_singleton: Optional[EmailBackend] = None


def get_backend() -> EmailBackend:
    """Lazily build the backend once per process. Tests can monkeypatch this."""
    global _backend_singleton
    if _backend_singleton is None:
        _backend_singleton = build_backend_from_env()
        log.info("Email backend initialized: %s", _backend_singleton.name)
    return _backend_singleton


def send_email(*, to: str, subject: str, text: str, html: Optional[str] = None) -> None:
    """Dispatch through the configured backend. Raises on hard SMTP failure."""
    backend = get_backend()
    backend.send(to=to, subject=subject, text=text, html=html)
