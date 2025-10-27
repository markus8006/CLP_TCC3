"""Infrastructure for industrial communication adapters.

This module defines :class:`BaseAdapter`, the common contract for adapters
capable of communicating with different types of PLCs.  Besides establishing
an async interface, the class centralises convenience helpers for subclasses
such as address normalisation, result payload creation and alarm lookup.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Union

from src.repository.Alarms_repository import AlarmDefinitionRepo

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Base contract used by every protocol adapter.

    Concrete implementations must provide asynchronous ``connect`` and
    ``disconnect`` operations together with the logic required to read PLC
    registers.  The base class offers a couple of quality-of-life helpers that
    keep the adapters small and consistent across protocols.
    """

    def __init__(self, orm: Any):
        self.orm = orm
        self._alarm_repo = AlarmDefinitionRepo()
        self._connected: bool = False
        self._lock = asyncio.Lock()

        raw_protocol = str(getattr(orm, "protocol", "")).lower()
        self.protocol_name = raw_protocol.split("-", 1)[0] if raw_protocol else ""
        self._simulation_mode = bool(getattr(orm, "use_simulation", False) or raw_protocol.endswith("-sim"))

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    async def connect(self) -> bool:
        """Establish the connection with the remote PLC."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection with the remote PLC."""

    @abstractmethod
    async def read_register(self, register_config: Any) -> Optional[Dict[str, Any]]:
        """Read a single register from the PLC."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def read_registers(self, registers: Iterable[Any]) -> List[Dict[str, Any]]:
        """Read multiple registers sequentially.

        The default implementation simply iterates over the provided iterable
        and awaits :meth:`read_register`.  Subclasses can override this method
        if they support more efficient bulk reads.
        """

        results: List[Dict[str, Any]] = []
        for register in registers:
            result = await self.read_register(register)
            if result:
                results.append(result)
        return results

    def is_connected(self) -> bool:
        return self._connected

    def _set_connected(self, state: bool) -> None:
        self._connected = state

    def in_simulation(self) -> bool:
        return self._simulation_mode

    # The alarm repository is lazily instanced above; this helper keeps the
    # actual lookup isolated.
    def _verify_alarm(self, register_id: Union[int, str]):
        try:
            return self._alarm_repo.alarm_by_register_id(register_id)
        except Exception:
            logger.exception("Erro ao verificar alarmes para registrador %s", register_id)
            return None

    def _build_result(
        self,
        register_id: Any,
        raw_value: Any,
        *,
        value_float: Optional[float] = None,
        value_int: Optional[int] = None,
        quality: str = "good",
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create a consistent payload with metadata returned by adapters."""

        ts = timestamp or datetime.now(timezone.utc)
        return {
            "plc_id": getattr(self.orm, "id", None),
            "register_id": register_id,
            "raw_value": raw_value,
            "value_float": value_float,
            "value_int": value_int,
            "quality": quality,
            "timestamp": ts,
        }

    @staticmethod
    def _normalise_address(address: Any) -> Union[int, str]:
        """Attempt to coerce the given address into an ``int`` when possible."""

        if isinstance(address, str):
            addr = address.strip()
            if not addr:
                return 0
            if addr.isdigit():
                return int(addr)
            try:
                return int(addr, 0)
            except ValueError:
                return addr
        return address

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
