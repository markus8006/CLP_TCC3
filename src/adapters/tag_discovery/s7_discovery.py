"""Descoberta simbólica para controladores Siemens S7."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from .base import TagDiscovery


class S7TagDiscovery(TagDiscovery):
    """Utiliza python-snap7 quando a tabela simbólica está disponível."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            import snap7
        except ImportError as exc:  # pragma: no cover - depende de pacote externo
            raise RuntimeError("A biblioteca python-snap7 é necessária para S7") from exc

        address = connection_params.get("address") or connection_params.get("host") or connection_params.get("ip")
        rack = int(connection_params.get("rack", 0))
        slot = int(connection_params.get("slot", 1))

        if not address:
            raise ValueError("Informe 'address' ou 'host' para o CLP Siemens")

        def _load() -> List[Dict[str, Any]]:
            client = snap7.client.Client()
            client.connect(address, rack, slot)
            try:
                if not hasattr(client, "get_symbol_table"):
                    raise RuntimeError(
                        "O servidor S7 não expõe a tabela simbólica. Configure ou forneça CSV."
                    )

                table = client.get_symbol_table()
                tags = []
                for entry in table:
                    tags.append(
                        {
                            "tag_name": entry.get("name"),
                            "address": entry.get("address"),
                            "data_type": entry.get("type"),
                            "source": "s7",
                        }
                    )
                return tags
            finally:
                client.disconnect()

        return await asyncio.to_thread(_load)


__all__ = ["S7TagDiscovery"]
