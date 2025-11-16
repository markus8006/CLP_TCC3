"""Driver simbólico simples para Modbus."""

from __future__ import annotations

from typing import Mapping

from src.models.tag_model import UniversalTag
from src.services.symbolic_drivers.base import SymbolicDriver
from src.simulations import sim_modbus


class ModbusSyntheticDriver(SymbolicDriver):
    protocol = "modbus"

    def default_symbol_provider(self, params: Mapping[str, object]):
        return sim_modbus.generate_symbol_table()

    def _apply_tag_defaults(self, tag: UniversalTag) -> UniversalTag:
        meta = self._metadata(tag)
        meta.setdefault("address", tag.metadata.get("address", tag.qualified_name))
        meta.setdefault("tag_name", tag.qualified_name)
        return tag
