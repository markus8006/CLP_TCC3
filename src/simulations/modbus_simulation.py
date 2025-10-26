"""Helper routines to seed the in-memory Modbus simulator."""

from __future__ import annotations

from typing import Iterable

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.simulations.runtime import simulation_registry
from src.utils.logs import logger


def seed_from_registers(registers: Iterable[Register]) -> None:
    """Populate the registry with deterministic values for each register."""

    for register in registers:
        identifier = getattr(register, "id", getattr(register, "address", None))
        if identifier is None:
            continue
        data_type = getattr(register, "data_type", "float")
        simulation_registry.set_static_value("modbus", identifier, 0, data_type=data_type)
        logger.debug("Registrador modbus %s registado na simulação", identifier)


def activate_plc_simulation(plc: PLC, registers: Iterable[Register]) -> None:
    """Convenience helper used by tests or CLI scripts to enable simulation."""

    plc.protocol = f"{plc.protocol}-sim" if not str(plc.protocol).endswith("-sim") else plc.protocol
    seed_from_registers(registers)


__all__ = ["seed_from_registers", "activate_plc_simulation"]

