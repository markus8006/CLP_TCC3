"""Thin SMTP wrapper used by the alarm service."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional, Sequence

from flask import has_app_context

from src.utils.logs import logger
from src.services.email_settings_service import get_email_settings
from src.app.settings import get_app_settings


def _normalise_recipients(recipients: Iterable[str]) -> Sequence[str]:
    unique = []
    seen = set()
    for recipient in recipients:
        if not recipient:
            continue
        value = recipient.strip()
        if not value or value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique


def send_email(
    subject: str,
    body: str,
    recipients: Iterable[str],
    *,
    html_body: Optional[str] = None,
) -> bool:
    """Send an email using the SMTP credentials defined in the Flask config."""

    normalised = _normalise_recipients(recipients)
    if not normalised:
        logger.debug("Nenhum destinatário válido para enviar email de alarme")
        return False

    if not has_app_context():
        logger.warning("Tentativa de envio de email fora do contexto da aplicação")
        return False

    config = get_email_settings()

    settings = get_app_settings()
    if not settings.features.enable_email:
        logger.info("Envio de email desativado pelas configurações da aplicação")
        return False

    suppress_send = config.get("MAIL_SUPPRESS_SEND")
    if suppress_send is None:
        suppress_send = settings.mail.suppress_send

    if suppress_send:
        logger.info("Envio de email suprimido (MAIL_SUPPRESS_SEND=True)")
        return True

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.get("MAIL_DEFAULT_SENDER") or settings.mail.default_sender
    message["To"] = ", ".join(normalised)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    server = config.get("MAIL_SERVER") or settings.mail.server
    port = int(config.get("MAIL_PORT") or settings.mail.port)
    username = config.get("MAIL_USERNAME") or settings.mail.username
    password = config.get("MAIL_PASSWORD") or settings.mail.password
    use_tls = bool(
        config.get("MAIL_USE_TLS")
        if config.get("MAIL_USE_TLS") is not None
        else settings.mail.use_tls
    )
    use_ssl = bool(
        config.get("MAIL_USE_SSL")
        if config.get("MAIL_USE_SSL") is not None
        else settings.mail.use_ssl
    )

    try:
        if use_ssl:
            smtp = smtplib.SMTP_SSL(server, port, timeout=10)
        else:
            smtp = smtplib.SMTP(server, port, timeout=10)

        with smtp:
            if use_tls and not use_ssl:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        logger.info("Email de alarme enviado para %s", normalised)
        return True
    except Exception:
        logger.exception("Erro ao enviar email de alarme para %s", normalised)
        return False


__all__ = ["send_email"]

