"""Serviços utilitários para descoberta de tags."""

from __future__ import annotations

from typing import Any, Dict, List


async def discover_tags(
    protocol: str, connection_params: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Executa a descoberta de tags para o protocolo solicitado."""

    raise RuntimeError(
        "Descoberta automática de tags indisponível após a migração para o poller Go via gRPC."
    )


__all__ = ["discover_tags"]
