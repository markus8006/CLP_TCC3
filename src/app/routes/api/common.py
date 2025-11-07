"""Shared helpers for API blueprints."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from src.models.PLCs import PLC
from src.models.Registers import Register

STATUS_LABELS = {
    "online": "Online",
    "offline": "Offline",
    "alarm": "Em alarme",
    "inactive": "Inativo",
}


def stringify(value: Any) -> str | None:
    """Return a human readable string for values coming from tag discovery."""

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value if item is not None and str(item).strip()]
        return " / ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def extract_address(entry: dict[str, Any]) -> str | None:
    direct = stringify(entry.get("address")) or stringify(entry.get("node_id"))
    if direct:
        return direct

    path = stringify(entry.get("path")) or stringify(entry.get("display_path"))
    if path:
        return path

    group = entry.get("group")
    variation = entry.get("variation")
    index = entry.get("index")
    if group is not None and variation is not None and index is not None:
        return f"g{group}v{variation}/{index}"

    if index is not None:
        subindex = entry.get("subindex")
        if subindex is not None:
            return f"{index}/{subindex}"
        return str(index)

    tag_name = stringify(entry.get("tag_name"))
    if tag_name:
        return tag_name

    return None


def extract_label(entry: dict[str, Any], fallback: str | None = None) -> str | None:
    label = (
        stringify(entry.get("tag_name"))
        or stringify(entry.get("name"))
        or stringify(entry.get("label"))
        or stringify(entry.get("display_path"))
    )
    if label:
        return label

    path = stringify(entry.get("path"))
    if path:
        return path

    node_id = stringify(entry.get("node_id"))
    if node_id:
        return node_id

    return fallback


def build_discovery_params(plc: PLC) -> dict[str, Any]:
    params: dict[str, Any] = {
        "ip": plc.ip_address,
        "host": plc.ip_address,
        "address": plc.ip_address,
        "port": plc.port,
    }

    protocol = (plc.protocol or "").lower()
    if protocol in {"modbus", "modbus-tcp", "modbus_rtu", "modbus-rtu"}:
        if plc.unit_id is not None:
            params["unit_id"] = plc.unit_id
            params["slave"] = plc.unit_id

    if protocol in {"s7", "siemens"} and plc.rack_slot:
        rack_slot = str(plc.rack_slot).replace(",", ".").split(".")
        try:
            params["rack"] = int(rack_slot[0])
        except (ValueError, IndexError):
            pass
        try:
            params["slot"] = int(rack_slot[1])
        except (ValueError, IndexError):
            pass

    return {key: value for key, value in params.items() if value not in (None, "")}


def await_sync(coro):
    """Execute a coroutine in a synchronous Flask context."""

    return asyncio.run(coro)


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())


def plc_status(plc: PLC, alarm_by_plc: dict[int, int]) -> str:
    if not plc.is_active:
        return "inactive"
    if alarm_by_plc.get(plc.id, 0) > 0:
        return "alarm"
    if plc.is_online:
        return "online"
    return "offline"


def register_status(register: Register, alarm_by_register: dict[int, int]) -> str:
    if not register.is_active:
        return "inactive"
    if alarm_by_register.get(register.id, 0) > 0:
        return "alarm"
    return "online"


def vlan_identifier(vlan_id: int | None) -> str:
    return "vlan-unset" if vlan_id is None else f"vlan-{vlan_id}"


def vlan_label(vlan_id: int | None) -> str:
    return "Rede Local" if vlan_id is None else f"VLAN {vlan_id}"


def vlan_value_from_key(key: str) -> int | None:
    if key == "vlan-unset":
        return None
    try:
        return int(key.split("-", 1)[1])
    except (IndexError, ValueError):
        return None


def utc_now() -> datetime:
    return datetime.utcnow()


__all__ = [
    "STATUS_LABELS",
    "await_sync",
    "build_discovery_params",
    "extract_address",
    "extract_label",
    "plc_status",
    "register_status",
    "status_label",
    "stringify",
    "utc_now",
    "vlan_identifier",
    "vlan_label",
    "vlan_value_from_key",
]
