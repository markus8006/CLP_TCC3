"""Helper routines to seed the IEC 104 simulation registry."""

from __future__ import annotations

from typing import Iterable

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.simulations.common import activate_protocol_simulation, seed_protocol_registers


def seed_from_registers(registers: Iterable[Register]) -> None:
    seed_protocol_registers("iec104", registers)


def activate_plc_simulation(plc: PLC, registers: Iterable[Register]) -> None:
    activate_protocol_simulation("iec104", plc, registers)


__all__ = ["seed_from_registers", "activate_plc_simulation"]
