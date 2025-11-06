"""Stub de discovery para Profinet baseado em ficheiros externos."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Dict, List

from .base import TagDiscovery


class ProfinetMappingDiscovery(TagDiscovery):
    """Lê definições indexadas a partir de CSV ou XLSX."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        mapping_file = connection_params.get("mapping_file")
        if not mapping_file:
            raise ValueError("Informe 'mapping_file' com o inventário Profinet")

        path = pathlib.Path(mapping_file)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {mapping_file}")

        def _load() -> List[Dict[str, Any]]:
            try:
                import pandas as pd  # type: ignore
            except ImportError as exc:  # pragma: no cover - depende de pacote externo
                raise RuntimeError(
                    "A biblioteca pandas é necessária para carregar mapas Profinet."
                ) from exc
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                frame = pd.read_excel(path)
            else:
                frame = pd.read_csv(path)

            data = []
            for row in frame.to_dict(orient="records"):
                data.append(
                    {
                        "tag_name": row.get("Tag") or row.get("tag"),
                        "index": row.get("Índice") or row.get("indice") or row.get("index"),
                        "subindex": row.get("Subíndice") or row.get("subindice") or row.get("subindex"),
                        "data_type": row.get("Tipo") or row.get("tipo"),
                        "description": row.get("Descrição") or row.get("descricao"),
                        "source": "profinet",
                    }
                )
            return data

        return await asyncio.to_thread(_load)


__all__ = ["ProfinetMappingDiscovery"]
