"""Serviço assíncrono para descoberta de tags baseada em drivers simbólicos."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from src.services.discovery_engine import as_dict_list, discovery_engine


async def discover_tags(protocol: str, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    params: Mapping[str, Any] = connection_params or {}
    tags = discovery_engine.discover(protocol, params)
    return as_dict_list(tags)


__all__ = ["discover_tags"]
