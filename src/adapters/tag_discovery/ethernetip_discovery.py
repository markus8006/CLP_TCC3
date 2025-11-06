"""Descoberta de tags para controladores Logix via EtherNet/IP."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from .base import TagDiscovery


class EthernetIPTagDiscovery(TagDiscovery):
    """Utiliza pycomm3 para obter a lista simbólica do CLP."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            from pycomm3 import LogixDriver
        except ImportError as exc:  # pragma: no cover - depende de pacote externo
            raise RuntimeError("A biblioteca pycomm3 é necessária para EtherNet/IP") from exc

        path = connection_params.get("path") or connection_params.get("host") or connection_params.get("ip")
        if not path:
            raise ValueError("Informe 'path' ou 'host' para conectar ao CLP Rockwell")

        slot = connection_params.get("slot")
        extra = {}
        if slot is not None:
            extra["slot"] = slot

        def _load() -> List[Dict[str, Any]]:
            with LogixDriver(path, **extra) as driver:
                tag_list = driver.get_tag_list()
                discovered = []
                for tag in tag_list:
                    name = tag.get("tag_name") or tag.get("name")
                    if not name:
                        continue
                    discovered.append(
                        {
                            "tag_name": name,
                            "data_type": tag.get("data_type") or tag.get("type"),
                            "dimensions": tag.get("dimensions"),
                            "source": "ethernetip",
                        }
                    )
                return discovered

        return await asyncio.to_thread(_load)


__all__ = ["EthernetIPTagDiscovery"]
