from __future__ import annotations

from typing import Any

from src.services.drivers.modbus_driver import ModbusDriver
from src.services.drivers.opcua_driver import OPCUADriver
from src.services.drivers.s7_driver import S7Driver
from src.utils.logs import logger


def get_driver(plc: Any):
    protocolo = (getattr(plc, "protocol", "") or "").lower()

    if protocolo in {"modbus", "modbus-tcp", "modbus_sim", "modbus-sim"}:
        return ModbusDriver(plc)
    if protocolo in {"s7", "s7-sim", "siemens"}:
        return S7Driver(plc)
    if protocolo in {"opcua", "opc-ua", "opcua-sim"}:
        return OPCUADriver(plc)

    logger.error("[POLLING] Protocolo desconhecido para CLP %s: %s", getattr(plc, "id", "?"), protocolo)
    return None
