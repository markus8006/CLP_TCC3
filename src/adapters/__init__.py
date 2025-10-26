"""Coleção de adapters de comunicação industrial."""

from .base_adapters import BaseAdapter
from .factory import get_adapter
from .modbus_adapter import ModbusAdapter
from .opcua_adapter import OpcUaAdapter
from .s7_adapter import S7Adapter

__all__ = [
    "BaseAdapter",
    "get_adapter",
    "ModbusAdapter",
    "OpcUaAdapter",
    "S7Adapter",
]
