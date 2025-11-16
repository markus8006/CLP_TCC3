"""Estruturas auxiliares para representar tags em um modelo universal.

Este módulo concentra toda a lógica para manipular tags simbólicas
independentemente do protocolo, permitindo que a camada de descoberta
converta as informações específicas de cada driver em uma árvore
normalizada que pode ser reutilizada pela API e pelo serviço de polling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


def _normalise_path(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    value = value.replace("\\", "/")
    segments = [segment for segment in value.split("/") if segment]
    return ".".join(segments) if segments else value


@dataclass(frozen=True)
class TagArrayInfo:
    """Metadados associados a tags que representam arrays."""

    dimensions: Tuple[int, ...] = ()
    element_type: Optional[str] = None

    @property
    def is_array(self) -> bool:
        return any(self.dimensions)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"dimensions": list(self.dimensions)}
        if self.element_type:
            payload["element_type"] = self.element_type
        payload["is_array"] = self.is_array
        return payload


@dataclass
class UniversalTag:
    """Representa um nó da árvore de tags independentemente do protocolo."""

    name: str
    qualified_name: str
    data_type: str
    display_name: Optional[str] = None
    array: Optional[TagArrayInfo] = None
    udt_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List["UniversalTag"] = field(default_factory=list)

    def add_child(self, child: "UniversalTag") -> None:
        self.children.append(child)

    def iter_leaves(self) -> Iterator["UniversalTag"]:
        if not self.children:
            yield self
            return
        for child in self.children:
            yield from child.iter_leaves()

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "data_type": self.data_type,
            "display_name": self.display_name,
            "udt_name": self.udt_name,
            "metadata": self.metadata,
        }
        if self.array:
            payload["array"] = self.array.to_dict()
        if self.children:
            payload["children"] = [child.to_dict() for child in self.children]
        return payload

    def clone(self, *, parent: Optional[str] = None) -> "UniversalTag":
        qualified = self.qualified_name
        if parent:
            qualified = f"{parent}.{self.name}" if self.name else parent
        return UniversalTag(
            name=self.name,
            qualified_name=qualified,
            data_type=self.data_type,
            display_name=self.display_name,
            array=self.array,
            udt_name=self.udt_name,
            metadata=dict(self.metadata),
            children=[child.clone(parent=qualified) for child in self.children],
        )

    @classmethod
    def from_symbol(
        cls,
        payload: Dict[str, Any],
        *,
        parent_path: str = "",
    ) -> "UniversalTag":
        raw_name = (
            payload.get("name")
            or payload.get("tag_name")
            or payload.get("label")
            or payload.get("qualified_name")
            or payload.get("display_name")
            or "tag"
        )
        name = str(raw_name).strip()
        qualified = payload.get("qualified_name")
        if not qualified:
            path = payload.get("path") or payload.get("display_path")
            if path:
                qualified = _normalise_path(str(path))
            else:
                qualified = f"{parent_path}.{name}" if parent_path else name
        display = payload.get("display_name") or payload.get("display_path")
        dtype = str(payload.get("data_type") or payload.get("type") or "unknown")
        udt_name = payload.get("udt") or payload.get("udt_name")
        array_dims: Sequence[int] = payload.get("dimensions") or payload.get(
            "array_dimensions", []
        )
        array: Optional[TagArrayInfo] = None
        if array_dims:
            element_type = payload.get("element_type") or payload.get("data_type")
            array = TagArrayInfo(tuple(int(dim) for dim in array_dims), element_type)

        metadata = dict(payload.get("metadata") or {})
        for key in ("address", "node_id", "path", "display_path"):
            if key in payload and key not in metadata:
                metadata[key] = payload[key]
        metadata.setdefault("qualified_name", qualified)

        tag = cls(
            name=name,
            qualified_name=qualified,
            data_type=dtype,
            display_name=display,
            array=array,
            udt_name=udt_name,
            metadata=metadata,
        )

        for child_payload in payload.get("children", []):
            child = cls.from_symbol(child_payload, parent_path=qualified)
            tag.add_child(child)
        return tag


def flatten_tags(tags: Iterable[UniversalTag]) -> List[UniversalTag]:
    flattened: List[UniversalTag] = []
    for tag in tags:
        flattened.extend(list(tag.iter_leaves()))
    return flattened


__all__ = ["UniversalTag", "TagArrayInfo", "flatten_tags"]
