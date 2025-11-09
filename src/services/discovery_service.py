"""Serviços auxiliares para controlar a descoberta de rede."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.repository.Settings_repository import SettingsRepoInstance
from src.utils.logs import logger
from src.utils.network import (
    DISCOVERY_FILE,
    DISCOVERY_SUMMARY_FILE,
    has_network_privileges,
    run_enhanced_discovery,
)

DISCOVERY_ENABLED_KEY = "network_discovery_enabled"
DISCOVERY_LAST_RUN_KEY = "network_discovery_last_run"


def is_discovery_enabled(default: bool = False) -> bool:
    """Retorna o estado persistido para a descoberta de rede."""

    return SettingsRepoInstance.get_bool(DISCOVERY_ENABLED_KEY, default)


def set_discovery_enabled(enabled: bool, *, actor: Optional[str] = None) -> None:
    """Atualiza o estado persistido responsável por habilitar a descoberta de rede."""

    description = "Estado da descoberta de rede"
    if actor:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        description = f"{description} ajustado por {actor} em {timestamp or 'UTC'}"
    SettingsRepoInstance.set_bool(
        DISCOVERY_ENABLED_KEY,
        enabled,
        description=description,
    )


def execute_discovery(*, actor: Optional[str] = None, **kwargs: Any) -> List[Dict[str, Any]]:
    """Executa a descoberta completa e regista o instante da operação."""

    results = run_enhanced_discovery(**kwargs)
    timestamp = datetime.now(timezone.utc).isoformat()
    description = "Última execução da descoberta de rede"
    if actor:
        description = f"{description} por {actor}"
    SettingsRepoInstance.set_value(
        DISCOVERY_LAST_RUN_KEY,
        timestamp,
        description=description,
    )
    return results


def get_last_run_time() -> Optional[datetime]:
    """Obtém o instante da última execução registada."""

    setting = SettingsRepoInstance.get_by_key(DISCOVERY_LAST_RUN_KEY)
    if not setting or not setting.value:
        return None
    try:
        return datetime.fromisoformat(setting.value)
    except ValueError:  # pragma: no cover - valor inesperado
        logger.debug("Valor de timestamp inválido para descoberta: %s", setting.value)
        return None


def load_discovery_results() -> List[Dict[str, Any]]:
    """Carrega o ficheiro completo de resultados da descoberta."""

    try:
        with DISCOVERY_FILE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return []
    except Exception:  # pragma: no cover - defensivo
        logger.exception("Erro ao ler resultados de descoberta")
        return []


def load_discovery_summary(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Carrega o resumo de dispositivos detectados."""

    try:
        with DISCOVERY_SUMMARY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        data = []
    except Exception:  # pragma: no cover - defensivo
        logger.exception("Erro ao ler resumo de descoberta")
        data = []

    if limit is not None:
        return data[:limit]
    return data


def count_industrial_devices(summary: Optional[List[Dict[str, Any]]] = None) -> int:
    """Conta quantos dispositivos do resumo foram classificados como industriais."""

    summary = summary if summary is not None else load_discovery_summary()
    return sum(1 for entry in summary if entry.get("is_industrial"))


__all__ = [
    "DISCOVERY_ENABLED_KEY",
    "DISCOVERY_LAST_RUN_KEY",
    "count_industrial_devices",
    "execute_discovery",
    "get_last_run_time",
    "has_network_privileges",
    "is_discovery_enabled",
    "load_discovery_results",
    "load_discovery_summary",
    "set_discovery_enabled",
]
