"""Classes utilitárias compartilhadas pelos drivers simbólicos."""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Mapping, MutableMapping

from src.models.tag_model import UniversalTag

SymbolTable = Iterable[Mapping[str, Any]]
SymbolProvider = Callable[[Mapping[str, Any]], SymbolTable]


class SymbolicDriver:
    """Classe base para drivers responsáveis por scraping simbólico."""

    protocol: str = "generic"

    def __init__(self, *, symbol_provider: SymbolProvider | None = None) -> None:
        self._symbol_provider = symbol_provider or self.default_symbol_provider

    def default_symbol_provider(self, params: Mapping[str, Any]) -> SymbolTable:
        raise RuntimeError(
            f"Driver simbólico para {self.protocol} não possui provider configurado."
        )

    def discover(self, params: Mapping[str, Any]) -> List[UniversalTag]:
        entries = list(self._symbol_provider(params))
        tags = [UniversalTag.from_symbol(entry) for entry in entries]
        return [self._finalise(tag) for tag in tags]

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    def _finalise(self, tag: UniversalTag) -> UniversalTag:
        tag.metadata.setdefault("protocol", self.protocol)
        tag.children = [self._finalise(child) for child in tag.children]
        return self._apply_tag_defaults(tag)

    def _apply_tag_defaults(self, tag: UniversalTag) -> UniversalTag:
        return tag

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _metadata(tag: UniversalTag) -> MutableMapping[str, Any]:
        if not isinstance(tag.metadata, MutableMapping):
            tag.metadata = dict(tag.metadata)
        return tag.metadata
