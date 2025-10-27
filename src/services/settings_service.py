"""Serviços auxiliares para gestão de configurações persistentes."""

from __future__ import annotations

from typing import Optional

from flask import current_app

from src.repository.Settings_repository import SettingsRepoInstance
from src.services.polling_runtime import set_runtime_enabled, trigger_polling_refresh
from src.utils.logs import logger

POLLING_ENABLED_KEY = "polling_enabled"


def get_polling_enabled(default: bool = True) -> bool:
    return SettingsRepoInstance.get_bool(POLLING_ENABLED_KEY, default=default)


def set_polling_enabled(
    enabled: bool,
    *,
    actor: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    SettingsRepoInstance.set_bool(POLLING_ENABLED_KEY, enabled, description=description or "Estado global do polling")
    app = current_app._get_current_object()
    set_runtime_enabled(app, enabled)
    trigger_polling_refresh(app)
    logger.process(
        "Polling %s por %s",
        "ativado" if enabled else "desativado",
        actor or "sistema",
    )
