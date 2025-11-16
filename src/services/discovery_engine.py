"""Motor de descoberta simbólica responsável por orquestrar os drivers."""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Mapping, Sequence, Type

from src.models.tag_model import UniversalTag, flatten_tags
from src.services.symbolic_drivers import (
    ADSyntheticDriver,
    CIPSyntheticDriver,
    ModbusSyntheticDriver,
    OPCUASyntheticDriver,
    S7SyntheticDriver,
    SymbolicDriver,
)

DriverFactory = Type[SymbolicDriver]


class DiscoveryEngine:
    """Registro centralizado dos drivers simbólicos."""

    def __init__(self) -> None:
        self._drivers: Dict[str, DriverFactory] = {}
        self._aliases: Dict[str, str] = {}
        self._lock = threading.RLock()

    def register_driver(
        self,
        key: str,
        driver_cls: DriverFactory,
        *,
        aliases: Sequence[str] | None = None,
    ) -> None:
        if not key:
            raise ValueError("Informe a chave do protocolo.")
        normalised = key.lower()
        with self._lock:
            self._drivers[normalised] = driver_cls
            for alias in aliases or ():
                self._aliases[alias.lower()] = normalised

    def resolve_key(self, protocol: str) -> str:
        if not protocol:
            raise ValueError("Informe o protocolo para descoberta.")
        key = protocol.lower()
        with self._lock:
            return self._aliases.get(key, key)

    def create_driver(self, protocol: str) -> SymbolicDriver:
        key = self.resolve_key(protocol)
        with self._lock:
            driver_cls = self._drivers.get(key)
        if driver_cls is None:
            raise ValueError(f"Protocolo {protocol!r} não possui driver configurado.")
        return driver_cls()

    def discover(self, protocol: str, params: Mapping[str, object]) -> List[UniversalTag]:
        driver = self.create_driver(protocol)
        tags = driver.discover(params)
        return tags

    def available_protocols(self) -> List[str]:
        with self._lock:
            return sorted(self._drivers.keys())


def _build_default_engine() -> DiscoveryEngine:
    engine = DiscoveryEngine()
    engine.register_driver(
        "opcua",
        OPCUASyntheticDriver,
        aliases=["opc-ua", "opcua-sim"],
    )
    engine.register_driver(
        "ethernetip",
        CIPSyntheticDriver,
        aliases=["ethernet/ip", "cip"],
    )
    engine.register_driver(
        "beckhoff",
        ADSyntheticDriver,
        aliases=["beckhoff-ads", "ads"],
    )
    engine.register_driver(
        "s7",
        S7SyntheticDriver,
        aliases=["siemens", "s7-sim"],
    )
    engine.register_driver(
        "modbus",
        ModbusSyntheticDriver,
        aliases=["modbus-tcp", "modbus-rtu", "modbus-sim"],
    )
    return engine


discovery_engine = _build_default_engine()


def as_dict_list(tags: Iterable[UniversalTag]) -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for tag in flatten_tags(tags):
        entry: Dict[str, object] = {
            "qualified_name": tag.qualified_name,
            "data_type": tag.data_type,
            "tag_name": tag.metadata.get("tag_name") or tag.qualified_name,
            "source": tag.metadata.get("protocol"),
            "metadata": tag.metadata,
            "hierarchy": tag.to_dict(),
        }
        if tag.array:
            entry["dimensions"] = list(tag.array.dimensions)
        if tag.udt_name:
            entry["udt"] = tag.udt_name
        for key in ("address", "node_id", "path", "display_path"):
            value = tag.metadata.get(key)
            if value is not None:
                entry[key] = value
        payload.append(entry)
    return payload


__all__ = ["discovery_engine", "DiscoveryEngine", "as_dict_list"]
