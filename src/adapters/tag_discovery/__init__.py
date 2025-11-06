"""Factories e implementações para descoberta automática de tags."""

from __future__ import annotations

from typing import Dict, Type

from .base import TagDiscovery
from .opcua_discovery import OpcUaTagDiscovery
from .ethernetip_discovery import EthernetIPTagDiscovery
from .beckhoff_ads_discovery import BeckhoffAdsTagDiscovery
from .s7_discovery import S7TagDiscovery
from .modbus_discovery import ModbusMappingDiscovery
from .profinet_discovery import ProfinetMappingDiscovery
from .dnp3_discovery import DNP3MappingDiscovery

_DISCOVERY_MAP: Dict[str, Type[TagDiscovery]] = {
    "opcua": OpcUaTagDiscovery,
    "opc-ua": OpcUaTagDiscovery,
    "ethernetip": EthernetIPTagDiscovery,
    "ethernet/ip": EthernetIPTagDiscovery,
    "cip": EthernetIPTagDiscovery,
    "beckhoff": BeckhoffAdsTagDiscovery,
    "beckhoff-ads": BeckhoffAdsTagDiscovery,
    "ads": BeckhoffAdsTagDiscovery,
    "s7": S7TagDiscovery,
    "siemens": S7TagDiscovery,
    "modbus": ModbusMappingDiscovery,
    "modbus-tcp": ModbusMappingDiscovery,
    "modbus-rtu": ModbusMappingDiscovery,
    "profinet": ProfinetMappingDiscovery,
    "dnp3": DNP3MappingDiscovery,
}


def get_discovery(protocol: str) -> TagDiscovery:
    """Retorna a implementação de descoberta para o protocolo indicado."""

    if not protocol:
        raise ValueError("Informe o protocolo para descobrir tags")

    try:
        discovery_cls = _DISCOVERY_MAP[protocol.lower()]
    except KeyError as exc:
        supported = ", ".join(sorted(_DISCOVERY_MAP))
        raise ValueError(
            f"Protocolo {protocol!r} não suportado para discovery. Opções: {supported}."
        ) from exc
    return discovery_cls()


__all__ = [
    "TagDiscovery",
    "OpcUaTagDiscovery",
    "EthernetIPTagDiscovery",
    "BeckhoffAdsTagDiscovery",
    "S7TagDiscovery",
    "ModbusMappingDiscovery",
    "ProfinetMappingDiscovery",
    "DNP3MappingDiscovery",
    "get_discovery",
]
