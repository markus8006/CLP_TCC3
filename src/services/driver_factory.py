"""Fábrica responsável por gerar a configuração enviada ao poller em Go."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

DriverBuilder = Callable[[Any, Iterable[Any]], Dict[str, Any]]


class GoDriverFactory:
    def __init__(self) -> None:
        self._builders: Dict[str, DriverBuilder] = {}
        self._aliases: Dict[str, str] = {}

    def register(
        self,
        protocol: str,
        builder: DriverBuilder,
        *,
        aliases: Iterable[str] | None = None,
    ) -> None:
        key = protocol.lower()
        self._builders[key] = builder
        for alias in aliases or ():
            self._aliases[alias.lower()] = key

    def resolve_protocol(self, protocol: str) -> str:
        if not protocol:
            raise ValueError("Informe o protocolo do CLP.")
        key = protocol.lower()
        return self._aliases.get(key, key)

    def build_payload(self, plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
        protocol = self.resolve_protocol(getattr(plc, "protocol", ""))
        try:
            builder = self._builders[protocol]
        except KeyError as exc:
            raise ValueError(f"Protocolo {protocol!r} não possui builder registrado.") from exc
        return builder(plc, registers)


def _common_connection(plc: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    host = getattr(plc, "ip_address", None) or getattr(plc, "host", None)
    if host:
        payload["host"] = host
    port = getattr(plc, "port", None)
    if port:
        payload["port"] = port
    timeout = getattr(plc, "timeout", None)
    if timeout:
        payload["timeout_ms"] = timeout
    retries = getattr(plc, "retry_count", None)
    if retries is not None:
        payload["retries"] = retries
    return payload


def _resolve_interval(plc: Any) -> int:
    interval = getattr(plc, "polling_interval", None)
    return int(interval) if interval else 1000


def _serialize_register(register: Any) -> Dict[str, Any]:
    address = (
        getattr(register, "address", None)
        or getattr(register, "node_id", None)
        or getattr(register, "tag", None)
        or getattr(register, "tag_name", None)
        or getattr(register, "name", None)
    )
    if not address:
        raise ValueError("Registro sem endereço não pode ser enviado ao poller.")
    payload: Dict[str, Any] = {
        "id": getattr(register, "id", None),
        "name": getattr(register, "tag", None)
        or getattr(register, "tag_name", None)
        or getattr(register, "name", str(address)),
        "address": str(address),
        "data_type": getattr(register, "data_type", None) or "float",
    }
    poll_rate = getattr(register, "poll_rate", None)
    if poll_rate:
        payload["poll_rate"] = poll_rate
    unit = getattr(register, "unit", None)
    if unit:
        payload.setdefault("metadata", {})["unit"] = unit
    return payload


def _session_payload(protocol: str, plc: Any, registers: Iterable[Any], connection: Mapping[str, Any]) -> Dict[str, Any]:
    tags = [_serialize_register(register) for register in registers]
    return {
        "sessions": [
            {
                "id": getattr(plc, "id", None),
                "plc_id": getattr(plc, "id", None),
                "name": getattr(plc, "name", None) or f"PLC-{getattr(plc, 'id', 'unknown')}",
                "protocol": protocol,
                "interval_ms": _resolve_interval(plc),
                "connection": dict(connection),
                "tags": tags,
            }
        ]
    }


def _modbus_builder(plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
    connection = _common_connection(plc)
    unit_id = getattr(plc, "unit_id", None)
    if unit_id is not None:
        connection["unit_id"] = unit_id
    return _session_payload("modbus", plc, registers, connection)


def _s7_builder(plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
    connection = _common_connection(plc)
    rack_slot = getattr(plc, "rack_slot", None)
    if rack_slot:
        parts = str(rack_slot).replace(";", ".").replace(",", ".").split(".")
        if parts and parts[0]:
            connection["rack"] = int(parts[0])
        if len(parts) > 1 and parts[1]:
            connection["slot"] = int(parts[1])
    return _session_payload("s7", plc, registers, connection)


def _opcua_builder(plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
    connection = _common_connection(plc)
    host = connection.get("host")
    port = connection.get("port", 4840)
    if host:
        connection.setdefault("endpoint", f"opc.tcp://{host}:{port}")
    return _session_payload("opcua", plc, registers, connection)


def _ethernetip_builder(plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
    connection = _common_connection(plc)
    slot = None
    rack_slot = getattr(plc, "rack_slot", None)
    if rack_slot:
        parts = str(rack_slot).replace(",", ".").split(".")
        if parts:
            slot = parts[-1]
    if slot is not None:
        connection["slot"] = slot
    return _session_payload("ethernetip", plc, registers, connection)


def _ads_builder(plc: Any, registers: Iterable[Any]) -> Dict[str, Any]:
    connection = _common_connection(plc)
    ams = getattr(plc, "ams_net_id", None)
    if ams:
        connection["ams_net_id"] = ams
    return _session_payload("beckhoff", plc, registers, connection)


def build_default_factory() -> GoDriverFactory:
    factory = GoDriverFactory()
    factory.register(
        "modbus",
        _modbus_builder,
        aliases=["modbus-tcp", "modbus-rtu", "modbus-sim"],
    )
    factory.register(
        "s7",
        _s7_builder,
        aliases=["siemens", "s7-sim"],
    )
    factory.register(
        "opcua",
        _opcua_builder,
        aliases=["opc-ua", "opcua-sim"],
    )
    factory.register(
        "ethernetip",
        _ethernetip_builder,
        aliases=["cip", "ethernet/ip"],
    )
    factory.register(
        "beckhoff",
        _ads_builder,
        aliases=["ads", "beckhoff-ads"],
    )
    return factory


driver_factory = build_default_factory()


__all__ = ["driver_factory", "GoDriverFactory", "build_default_factory"]
