"""Motor de normalização de endereços de registradores."""

from __future__ import annotations

import re
from typing import Any, Dict


class AddressMappingEngine:
    """Responsável por normalizar endereços de registradores para um formato comum."""

    _SIEMENS_REGEX = re.compile(
        r"DB(?P<db>\d+)\.(?P<area>DB[XYDBW]+)(?P<byte>\d+)(?:\.(?P<bit>\d+))?",
        re.IGNORECASE,
    )

    _MODBUS_REGEX = re.compile(r"(?P<function>[1-6])(?P<address>\d{4,5})")

    def normalize(self, protocol: str, address: str) -> Dict[str, Any]:
        if not protocol:
            raise ValueError("Protocolo é obrigatório para normalização")
        if not address:
            raise ValueError("Endereço é obrigatório para normalização")

        key = protocol.lower()
        if key in {"siemens", "s7"}:
            return self._normalize_siemens(address)
        if key in {"modbus", "modbus-tcp", "modbus-rtu"}:
            return self._normalize_modbus(address)
        if key in {"ethernetip", "ethernet/ip", "cip"}:
            return {"tag": address}
        if key in {"opcua", "opc-ua"}:
            return {"node_id": address}
        if key in {"profinet", "dnp3", "iec104", "iec-104"}:
            return {"index": address}
        return {"raw": address}

    def _normalize_siemens(self, address: str) -> Dict[str, Any]:
        match = self._SIEMENS_REGEX.match(address.replace(" ", ""))
        if not match:
            raise ValueError(f"Endereço Siemens inválido: {address}")
        groups = match.groupdict()
        byte_offset = int(groups.get("byte") or 0)
        bit = groups.get("bit")
        bit_offset = int(bit) if bit is not None else None
        return {
            "db": int(groups["db"]),
            "area": groups["area"].upper(),
            "byte": byte_offset,
            "bit": bit_offset,
        }

    def _normalize_modbus(self, address: str) -> Dict[str, Any]:
        address = address.strip()
        if address.isdigit():
            function_code = int(address[0])
            register = int(address[1:])
            return {"function": function_code, "address": register}

        match = self._MODBUS_REGEX.match(address)
        if not match:
            raise ValueError(f"Endereço Modbus inválido: {address}")
        return {
            "function": int(match.group("function")),
            "address": int(match.group("address")),
        }


__all__ = ["AddressMappingEngine"]
