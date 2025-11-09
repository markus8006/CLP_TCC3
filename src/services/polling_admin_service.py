"""Funções de apoio para gerir o estado de polling via interface administrativa."""
from __future__ import annotations

from typing import Optional

from src.services.settings_service import set_polling_enabled


def update_polling_state(enabled: bool, *, actor: Optional[str] = None) -> None:
    """Atualiza a flag de polling persistida com metadados de auditoria."""

    set_polling_enabled(enabled, actor=actor)
