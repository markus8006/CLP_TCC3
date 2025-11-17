"""Serviços auxiliares para gestão de configurações persistentes."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from flask import current_app

from src.repository.Settings_repository import SettingsRepoInstance
from src.utils.logs import logger

if TYPE_CHECKING:
    from src.services.polling.polling_service import PollingService

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
    service = _get_polling_service(app)
    if service:
        service.set_enabled(enabled)
    logger.process(
        "Polling %s por %s",
        "ativado" if enabled else "desativado",
        actor or "sistema",
    )


def _get_polling_service(app) -> Optional[PollingService]:
    service = app.extensions.get("polling")
    return service if service is not None else None
