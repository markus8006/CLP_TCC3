"""Simulador simplificado da tabela simbólica S7."""

from __future__ import annotations

from typing import Dict, List

Symbol = Dict[str, object]


def generate_symbol_tree() -> List[Symbol]:
    return [
        {
            "name": "DB1",
            "data_type": "DB",
            "children": [
                {
                    "name": "Temperatura",
                    "data_type": "REAL",
                    "metadata": {"address": "DB1.DBW0"},
                },
                {
                    "name": "Nivel",
                    "data_type": "REAL",
                    "metadata": {"address": "DB1.DBW4"},
                },
                {
                    "name": "BombaAtiva",
                    "data_type": "BOOL",
                    "metadata": {"address": "DB1.DBX8.0"},
                },
            ],
        }
    ]


__all__ = ["generate_symbol_tree"]
