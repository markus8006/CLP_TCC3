"""Adapter implementation for Modbus TCP PLCs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

try:  # pragma: no cover - optional dependency
    from pymodbus.client import AsyncModbusTcpClient
except Exception:  # pragma: no cover - safeguard if library missing
    AsyncModbusTcpClient = None  # type: ignore

from src.adapters.base_adapters import BaseAdapter
from src.simulations.runtime import simulation_registry

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem
    from src.app.settings import AppSettings


class ModbusAdapter(BaseAdapter):
    """Async Modbus TCP adapter built on top of :mod:`pymodbus`."""

    def __init__(self, orm: Any, *, settings: Optional["AppSettings"] = None):
        super().__init__(orm, settings=settings)
        self.ip_address = getattr(self.orm, "ip_address", None)
        self.port = getattr(self.orm, "port", 502)
        timeout_ms = getattr(self.orm, "timeout", 3000) or 3000
        self.timeout = max(float(timeout_ms) / 1000.0, 0.1)
        self.client: Optional[AsyncModbusTcpClient] = None

    async def connect(self) -> bool:
        if self.in_simulation():
            self._set_connected(True)
            return True

        if AsyncModbusTcpClient is None:
            logger.error("pymodbus não está instalado; não é possível abrir conexão Modbus")
            self._set_connected(False)
            return False

        async with self._lock:
            if self.client and self.is_connected():
                return True

            self.client = AsyncModbusTcpClient(
                host=self.ip_address,
                port=self.port,
                timeout=self.timeout,
            )
            try:
                await self.client.connect()
            except Exception:  # pragma: no cover - dependente do ambiente
                logger.exception("Erro ao conectar ao PLC Modbus %s:%s", self.ip_address, self.port)
                self._set_connected(False)
                return False

            connected = getattr(self.client, "connected", True)
            self._set_connected(bool(connected))

            if self.is_connected():
                logger.info("Conectado ao PLC Modbus %s:%s", self.ip_address, self.port)
            return self.is_connected()

    async def disconnect(self) -> None:
        if self.in_simulation():
            self._set_connected(False)
            return

        async with self._lock:
            try:
                if self.client is not None:
                    close_fn = getattr(self.client, "close", None)
                    if asyncio.iscoroutinefunction(close_fn):
                        await close_fn()
                    elif callable(close_fn):
                        close_fn()
            except Exception:
                logger.exception("Erro ao desconectar do PLC Modbus %s", self.ip_address)
            finally:
                self._set_connected(False)
                self.client = None

    async def read_register(self, register_config: Any) -> Optional[Dict[str, Any]]:
        if self.in_simulation():
            simulated = simulation_registry.next_value(self.protocol_name or "modbus", register_config)
            return self._build_result(
                register_id=simulated["register_id"],
                raw_value=simulated["raw_value"],
                value_float=simulated["value_float"],
                value_int=simulated["value_int"],
                quality=simulated["quality"],
            )

        if not self.is_connected() or self.client is None:
            logger.debug("Tentativa de leitura Modbus sem conexão ativa")
            return None

        addr_raw = getattr(register_config, "address", 0)
        address = self._normalise_address(addr_raw)
        try:
            address_int = int(address)
        except (TypeError, ValueError):
            logger.warning("Endereço Modbus inválido: %s", address)
            return None

        reg_type = getattr(register_config, "register_type", "holding")
        slave = int(getattr(register_config, "slave", getattr(self.orm, "unit_id", 1) or 1))
        register_id = getattr(register_config, "id", None)
        data_type = getattr(register_config, "data_type", "int16")

        try:
            if reg_type == "holding":
                response = await self.client.read_holding_registers(address_int, count=1, slave=slave)
            elif reg_type == "input":
                response = await self.client.read_input_registers(address_int, count=1, slave=slave)
            elif reg_type == "coil":
                response = await self.client.read_coils(address_int, count=1, slave=slave)
            else:
                logger.warning("Tipo de registrador Modbus desconhecido: %s", reg_type)
                return None
        except Exception:
            logger.exception("Erro durante leitura do registrador %s", register_id)
            return None

        if hasattr(response, "isError") and response.isError():
            logger.warning("Resposta Modbus com erro: %s", response)
            return None

        raw_value: Optional[int] = None
        if hasattr(response, "registers") and response.registers:
            raw_value = response.registers[0]
        elif hasattr(response, "bits") and response.bits:
            raw_value = int(bool(response.bits[0]))

        value_float = self._convert_value(raw_value, data_type)
        value_int = self._coerce_int(raw_value)

        return self._build_result(
            register_id=register_id,
            raw_value=raw_value,
            value_float=value_float,
            value_int=value_int,
            quality="good" if raw_value is not None else "bad",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _convert_value(self, raw_value: Optional[int], data_type: str) -> Optional[float]:
        if raw_value is None:
            return None
        try:
            if data_type == "int16":
                return float(raw_value - 65536 if raw_value > 32767 else raw_value)
            if data_type == "uint16":
                return float(raw_value)
            if data_type == "bool":
                return float(bool(raw_value))
            return float(raw_value)
        except Exception:
            logger.warning("Erro ao converter valor %s para tipo %s", raw_value, data_type)
            return None
