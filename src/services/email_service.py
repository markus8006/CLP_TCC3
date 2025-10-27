"""Thin SMTP wrapper used by the alarm service."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable, Sequence

from flask import current_app

from src.utils.logs import logger


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


def send_email(subject: str, body: str, recipients: Iterable[str]) -> bool:
    """Send an email using the SMTP credentials defined in the Flask config."""

    normalised = _normalise_recipients(recipients)
    if not normalised:
        logger.debug("Nenhum destinatário válido para enviar email de alarme")
        return False

    try:
        config = current_app.config  # type: ignore[attr-defined]
    except RuntimeError:
        logger.warning("Tentativa de envio de email fora do contexto da aplicação")
        return False

    if config.get("MAIL_SUPPRESS_SEND"):
        logger.info("Envio de email suprimido (MAIL_SUPPRESS_SEND=True)")
        return True

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.get("MAIL_DEFAULT_SENDER", "alarms@example.com")
    message["To"] = ", ".join(normalised)
    message.set_content(body)

    server = config.get("MAIL_SERVER", "localhost")
    port = int(config.get("MAIL_PORT", 25))
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    use_tls = bool(config.get("MAIL_USE_TLS", False))
    use_ssl = bool(config.get("MAIL_USE_SSL", False))

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

