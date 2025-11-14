"""Helpers for persisting and retrieving SMTP settings for alarm emails."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from flask import current_app

from src.repository.Settings_repository import SettingsRepoInstance
from src.app.settings import get_app_settings

EMAIL_SETTING_KEYS = {
    "MAIL_SERVER",
    "MAIL_PORT",
    "MAIL_USERNAME",
    "MAIL_PASSWORD",
    "MAIL_USE_TLS",
    "MAIL_USE_SSL",
    "MAIL_DEFAULT_SENDER",
    "MAIL_SUPPRESS_SEND",
}

_BOOL_KEYS = {"MAIL_USE_TLS", "MAIL_USE_SSL", "MAIL_SUPPRESS_SEND"}
_INT_KEYS = {"MAIL_PORT"}


def _coerce_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in _BOOL_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        return text in {"1", "true", "on", "yes"}
    if key in _INT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value


def _stringify_value(key: str, value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if key in _BOOL_KEYS:
        return "1" if bool(value) else "0"
    return str(value)


def get_email_settings(*, include_defaults: bool = True) -> Dict[str, Any]:
    """Return the effective SMTP settings for the alarm email service."""

    settings: Dict[str, Any] = {}
    mail_defaults: Dict[str, Any] = {}
    if include_defaults:
        try:
            mail = get_app_settings().mail
            mail_defaults = {
                "MAIL_SERVER": mail.server,
                "MAIL_PORT": mail.port,
                "MAIL_USERNAME": mail.username,
                "MAIL_PASSWORD": mail.password,
                "MAIL_USE_TLS": mail.use_tls,
                "MAIL_USE_SSL": mail.use_ssl,
                "MAIL_DEFAULT_SENDER": mail.default_sender,
                "MAIL_SUPPRESS_SEND": mail.suppress_send,
            }
        except RuntimeError:
            try:
                app_config = current_app.config  # type: ignore[attr-defined]
            except RuntimeError:
                app_config = {}
            else:
                mail_defaults = {key: app_config.get(key) for key in EMAIL_SETTING_KEYS}

    for key in EMAIL_SETTING_KEYS:
        stored = SettingsRepoInstance.get_value(key)
        if stored not in (None, ""):
            settings[key] = _coerce_value(key, stored)
        elif include_defaults:
            settings[key] = _coerce_value(key, mail_defaults.get(key))
        else:
            settings[key] = None
    return settings


def get_stored_email_settings() -> Dict[str, Any]:
    """Return only the values persisted in the database (without defaults)."""

    stored: Dict[str, Any] = {}
    for key in EMAIL_SETTING_KEYS:
        value = SettingsRepoInstance.get_value(key)
        stored[key] = _coerce_value(key, value) if value not in (None, "") else None
    return stored


def update_email_settings(values: Mapping[str, Any]) -> None:
    """Persist the provided SMTP values, clearing keys that are empty."""

    for key in EMAIL_SETTING_KEYS:
        if key not in values:
            continue
        raw_value = values[key]
        string_value = _stringify_value(key, raw_value)
        if string_value is None:
            SettingsRepoInstance.delete_key(key)
        elif key in _BOOL_KEYS:
            SettingsRepoInstance.set_bool(key, bool(raw_value))
        else:
            SettingsRepoInstance.set_value(key, string_value)


def iter_email_settings() -> Iterable[str]:
    """Yield the known SMTP setting keys."""

    return tuple(EMAIL_SETTING_KEYS)


__all__ = [
    "EMAIL_SETTING_KEYS",
    "get_email_settings",
    "get_stored_email_settings",
    "update_email_settings",
    "iter_email_settings",
]
