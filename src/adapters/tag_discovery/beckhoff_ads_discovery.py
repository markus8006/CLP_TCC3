"""Descoberta de tags para controladores Beckhoff ADS."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from .base import TagDiscovery


class BeckhoffAdsTagDiscovery(TagDiscovery):
    """Usa pyads para listar variáveis globais do TwinCAT."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            import pyads
        except ImportError as exc:  # pragma: no cover - depende de pacote externo
            raise RuntimeError("A biblioteca pyads é necessária para Beckhoff ADS") from exc

        ams_net_id = connection_params.get("ams_net_id") or connection_params.get("target")
        ams_port = connection_params.get("ams_port", 851)
        if not ams_net_id:
            raise ValueError("Informe 'ams_net_id' do controlador Beckhoff")

        ip_address = connection_params.get("ip")

        def _load() -> List[Dict[str, Any]]:
            connection = pyads.Connection(ams_net_id, ams_port, ip_address=ip_address)
            connection.open()
            try:
                symbols = connection.get_all_symbols()
                tags = []
                for symbol in symbols:
                    tags.append(
                        {
                            "tag_name": symbol.name,
                            "data_type": symbol.plc_type,
                            "comment": symbol.comment,
                            "source": "beckhoff_ads",
                        }
                    )
                return tags
            finally:
                connection.close()

        return await asyncio.to_thread(_load)


__all__ = ["BeckhoffAdsTagDiscovery"]
