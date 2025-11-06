"""Stub de discovery para protocolos baseados em endereços Modbus."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Dict, List

from .base import TagDiscovery


class ModbusMappingDiscovery(TagDiscovery):
    """Lê um ficheiro CSV/XLSX contendo o mapa de registradores."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        mapping_file = connection_params.get("mapping_file")
        if not mapping_file:
            raise ValueError("Informe 'mapping_file' com o caminho para o CSV/XLSX do mapa")

        path = pathlib.Path(mapping_file)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo de mapeamento não encontrado: {mapping_file}")

        def _load() -> List[Dict[str, Any]]:
            try:
                import pandas as pd  # type: ignore
            except ImportError as exc:  # pragma: no cover - depende de pacote externo
                raise RuntimeError(
                    "A biblioteca pandas é necessária para carregar mapas Modbus."
                ) from exc
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                frame = pd.read_excel(path)
            else:
                frame = pd.read_csv(path)
            records = []
            for row in frame.to_dict(orient="records"):
                records.append(
                    {
                        "tag_name": row.get("Tag") or row.get("tag"),
                        "address": row.get("Endereço") or row.get("endereco") or row.get("address"),
                        "data_type": row.get("Tipo") or row.get("tipo"),
                        "unit": row.get("Unidade") or row.get("unidade"),
                        "description": row.get("Descrição") or row.get("descricao"),
                        "source": "modbus",
                    }
                )
            return records

        return await asyncio.to_thread(_load)


__all__ = ["ModbusMappingDiscovery"]
