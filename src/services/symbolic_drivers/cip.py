"""Driver simbólico para controladores EtherNet/IP (Rockwell CIP)."""

from __future__ import annotations

from typing import Mapping

from src.models.tag_model import UniversalTag
from src.services.symbolic_drivers.base import SymbolicDriver
from src.simulations import sim_cip


class CIPSyntheticDriver(SymbolicDriver):
    protocol = "ethernetip"

    def default_symbol_provider(self, params: Mapping[str, object]):
        return sim_cip.generate_symbol_tree()

    def _apply_tag_defaults(self, tag: UniversalTag) -> UniversalTag:
        meta = self._metadata(tag)
        meta.setdefault("tag_name", tag.qualified_name)
        meta.setdefault("address", tag.metadata.get("qualified_name", tag.qualified_name))
        return tag
