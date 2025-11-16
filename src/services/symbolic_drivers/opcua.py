"""Driver simbólico para servidores OPC UA."""

from __future__ import annotations

from typing import Mapping

from src.models.tag_model import UniversalTag
from src.services.symbolic_drivers.base import SymbolicDriver
from src.simulations import sim_opcua


class OPCUASyntheticDriver(SymbolicDriver):
    protocol = "opcua"

    def default_symbol_provider(self, params: Mapping[str, object]):
        return sim_opcua.generate_symbol_tree()

    def _apply_tag_defaults(self, tag: UniversalTag) -> UniversalTag:
        meta = self._metadata(tag)
        if "display_path" not in meta:
            meta["display_path"] = tag.qualified_name.replace(".", "/")
        if "node_id" in meta:
            meta.setdefault("address", meta["node_id"])
        else:
            meta.setdefault("address", meta.get("qualified_name", tag.qualified_name))
        return tag
