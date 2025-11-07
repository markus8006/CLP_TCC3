"""Helper routines to seed the OPC UA simulation registry."""

from __future__ import annotations

from typing import Iterable

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.simulations.common import activate_protocol_simulation, seed_protocol_registers


def seed_from_registers(registers: Iterable[Register]) -> None:
    seed_protocol_registers("opcua", registers)


def activate_plc_simulation(plc: PLC, registers: Iterable[Register]) -> None:
    activate_protocol_simulation("opcua", plc, registers)


__all__ = ["seed_from_registers", "activate_plc_simulation"]
