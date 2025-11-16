"""Driver simbólico para controladores Siemens S7."""

from __future__ import annotations

from typing import Mapping

from src.models.tag_model import UniversalTag
from src.services.symbolic_drivers.base import SymbolicDriver
from src.simulations import sim_s7


class S7SyntheticDriver(SymbolicDriver):
    protocol = "s7"

    def default_symbol_provider(self, params: Mapping[str, object]):
        return sim_s7.generate_symbol_tree()

    def _apply_tag_defaults(self, tag: UniversalTag) -> UniversalTag:
        meta = self._metadata(tag)
        if "address" not in meta:
            meta["address"] = tag.qualified_name
        meta.setdefault("tag_name", tag.qualified_name)
        return tag
