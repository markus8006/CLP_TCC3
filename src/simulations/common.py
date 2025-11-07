"""Common helpers for protocol-specific simulation seeders."""

from __future__ import annotations

from typing import Hashable, Iterable

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.simulations.runtime import simulation_registry
from src.utils.logs import logger


def _resolve_identifier(register: Register) -> Hashable | None:
    for attr in ("id", "address", "tag", "tag_name", "name"):
        value = getattr(register, attr, None)
        if value not in (None, ""):
            return value
    return None


def seed_protocol_registers(protocol: str, registers: Iterable[Register]) -> None:
    """Populate the simulation registry with deterministic values."""

    for register in registers:
        identifier = _resolve_identifier(register)
        if identifier is None:
            continue
        data_type = getattr(register, "data_type", "float") or "float"
        simulation_registry.set_static_value(protocol, identifier, 0, data_type=str(data_type))
        logger.debug(
            "Registrador %s/%s registado na simulação", protocol, identifier
        )


def activate_protocol_simulation(protocol: str, plc: PLC, registers: Iterable[Register]) -> None:
    """Mark the PLC as simulated and seed the registry for its registers."""

    if not str(getattr(plc, "protocol", "")).endswith("-sim"):
        plc.protocol = f"{protocol}-sim"
    seed_protocol_registers(protocol, registers)


__all__ = ["seed_protocol_registers", "activate_protocol_simulation"]
