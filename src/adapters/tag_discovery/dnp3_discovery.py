"""Stub de discovery para dispositivos DNP3 com mapa externo."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Dict, List

from .base import TagDiscovery


class DNP3MappingDiscovery(TagDiscovery):
    """DNP3 trabalha com índices, logo dependemos de um mapa externo."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        mapping_file = connection_params.get("mapping_file")
        if not mapping_file:
            raise ValueError("Informe 'mapping_file' com os índices DNP3")

        path = pathlib.Path(mapping_file)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {mapping_file}")

        def _load() -> List[Dict[str, Any]]:
            try:
                import pandas as pd  # type: ignore
            except ImportError as exc:  # pragma: no cover - depende de pacote externo
                raise RuntimeError(
                    "A biblioteca pandas é necessária para carregar mapas DNP3."
                ) from exc
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                frame = pd.read_excel(path)
            else:
                frame = pd.read_csv(path)

            entries = []
            for row in frame.to_dict(orient="records"):
                entries.append(
                    {
                        "tag_name": row.get("Tag") or row.get("tag"),
                        "index": row.get("Índice") or row.get("indice") or row.get("index"),
                        "group": row.get("Grupo") or row.get("grupo") or row.get("group"),
                        "variation": row.get("Variação") or row.get("variacao") or row.get("variation"),
                        "description": row.get("Descrição") or row.get("descricao"),
                        "source": "dnp3",
                    }
                )
            return entries

        return await asyncio.to_thread(_load)


__all__ = ["DNP3MappingDiscovery"]
