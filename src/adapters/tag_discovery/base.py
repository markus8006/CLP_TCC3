"""Definições base para descoberta de tags."""

from __future__ import annotations

import abc
from typing import Any, Dict, List


class TagDiscovery(abc.ABC):
    """Interface comum para mecanismos de discovery."""

    @abc.abstractmethod
    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retorna a lista de tags (com metadados) encontrada para o CLP."""


__all__ = ["TagDiscovery"]
