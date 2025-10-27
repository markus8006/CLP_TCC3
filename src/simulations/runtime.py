"""Runtime helpers that feed deterministic values to simulated adapters.

The real adapters transparently switch to this registry whenever the PLC
instance is flagged for simulation (for example by using the ``*-sim``
protocols).  This makes it possible to exercise the entire polling pipeline
without requiring a physical controller.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Hashable, Optional, Tuple

from src.utils.logs import logger


@dataclass
class SimulationEntry:
    """Internal structure that tracks the state of a simulated signal."""

    value: float
    step: float
    direction: int
    minimum: float
    maximum: float
    data_type: str
    fixed: bool = False


class SimulationRegistry:
    """Simple in-memory registry that produces pseudo-realistic values."""

    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, Hashable], SimulationEntry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def next_value(self, protocol: str, register_config: Any) -> Dict[str, Any]:
        """Return the next simulated value for the given register."""

        identifier = self._resolve_identifier(register_config)
        data_type = self._resolve_data_type(register_config)

        with self._lock:
            entry = self._entries.get((protocol, identifier))
            if entry is None:
                entry = self._create_entry(protocol, identifier, data_type)
                self._entries[(protocol, identifier)] = entry

            if entry.fixed:
                value = entry.value
            else:
                value = self._step_value(entry)

        value_float = self._coerce_float(value)
        value_int = self._coerce_int(value)
        quality = "good" if value is not None else "bad"

        return {
            "register_id": getattr(register_config, "id", None),
            "raw_value": value,
            "value_float": value_float,
            "value_int": value_int,
            "quality": quality,
        }

    def set_static_value(
        self,
        protocol: str,
        identifier: Hashable,
        value: Any,
        *,
        data_type: Optional[str] = None,
    ) -> None:
        """Override the simulated value for a register and freeze it."""

        dtype = (data_type or self._infer_type(value) or "float").lower()
        with self._lock:
            self._entries[(protocol, identifier)] = SimulationEntry(
                value=float(value) if isinstance(value, (int, float)) else float(self._coerce_float(value) or 0.0),
                step=0.0,
                direction=1,
                minimum=float(value) if isinstance(value, (int, float)) else 0.0,
                maximum=float(value) if isinstance(value, (int, float)) else 0.0,
                data_type=dtype,
                fixed=True,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _create_entry(self, protocol: str, identifier: Hashable, data_type: str) -> SimulationEntry:
        seed = abs(hash((protocol, identifier, time.time_ns()))) % 1000
        base = 10.0 + (seed % 25)
        step = 0.5 + (seed % 10) * 0.05
        minimum = base - 10.0
        maximum = base + 10.0

        dtype = data_type.lower()
        if dtype in {"bool", "boolean"}:
            base = float(seed % 2)
            step = 1.0
            minimum = 0.0
            maximum = 1.0
        elif dtype in {"int", "int16", "uint16", "int32", "dint"}:
            step = max(1.0, math.floor(step))

        logger.debug(
            "Criada entrada de simulação para %s/%s (dtype=%s base=%s step=%s)",
            protocol,
            identifier,
            data_type,
            base,
            step,
        )

        return SimulationEntry(
            value=base,
            step=step,
            direction=1,
            minimum=minimum,
            maximum=maximum,
            data_type=dtype,
        )

    def _step_value(self, entry: SimulationEntry) -> Any:
        dtype = entry.data_type
        if dtype in {"bool", "boolean"}:
            entry.value = 0.0 if entry.value else 1.0
            return bool(entry.value)

        entry.value += entry.step * entry.direction
        if entry.value >= entry.maximum or entry.value <= entry.minimum:
            entry.direction *= -1
            entry.value = max(min(entry.value, entry.maximum), entry.minimum)

        if dtype in {"int", "int16", "uint16", "int32", "dint"}:
            return int(round(entry.value))
        return round(entry.value, 3)

    def _resolve_identifier(self, register_config: Any) -> Hashable:
        if hasattr(register_config, "id") and getattr(register_config, "id") is not None:
            return getattr(register_config, "id")
        if hasattr(register_config, "address"):
            return getattr(register_config, "address")
        return id(register_config)

    def _resolve_data_type(self, register_config: Any) -> str:
        dtype = getattr(register_config, "data_type", None)
        if dtype:
            return str(dtype)
        return "float"

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _infer_type(self, value: Any) -> Optional[str]:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        return None


# Global registry reused by adapters
simulation_registry = SimulationRegistry()

__all__ = ["simulation_registry", "SimulationRegistry"]

