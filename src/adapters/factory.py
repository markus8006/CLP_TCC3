"""Factory utilitária para instanciar adapters de protocolos industriais."""

from __future__ import annotations

from typing import Any, Callable, Dict, Type

from src.adapters.base_adapters import BaseAdapter
from src.adapters.modbus_adapter import ModbusAdapter
from src.adapters.opcua_adapter import OpcUaAdapter
from src.adapters.s7_adapter import S7Adapter

AdaptersMap = Dict[str, Type[BaseAdapter]]


def _default_adapters() -> AdaptersMap:
    return {
        "modbus": ModbusAdapter,
        "modbus-sim": ModbusAdapter,
        "opcua": OpcUaAdapter,
        "opc-ua": OpcUaAdapter,
        "opcua-sim": OpcUaAdapter,
        "opc-ua-sim": OpcUaAdapter,
        "s7": S7Adapter,
        "siemens": S7Adapter,
        "s7-sim": S7Adapter,
        "siemens-sim": S7Adapter,
    }


def get_adapter(protocol: str, orm: Any, *, registry_factory: Callable[[], AdaptersMap] = _default_adapters) -> BaseAdapter:
    """Retorna uma instância de adapter para o protocolo solicitado."""

    if not protocol:
        raise ValueError("Protocolo não informado")

    registry = registry_factory()
    adapter_cls = registry.get(protocol.lower())
    if adapter_cls is None:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"Protocolo {protocol!r} não suportado. Opções: {supported}")
    return adapter_cls(orm)
