"""Serviços utilitários para descoberta de tags."""

from __future__ import annotations

from typing import Any, Dict, List

from src.adapters.tag_discovery import TagDiscovery, get_discovery


async def discover_tags(protocol: str, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Executa a descoberta de tags para o protocolo solicitado."""

    discovery: TagDiscovery = get_discovery(protocol)
    return await discovery.discover_tags(connection_params)


__all__ = ["discover_tags"]
