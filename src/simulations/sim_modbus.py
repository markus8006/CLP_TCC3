"""Simulação simples de registros Modbus."""

from __future__ import annotations

from typing import Dict, List

Symbol = Dict[str, object]


def generate_symbol_table() -> List[Symbol]:
    return [
        {
            "name": "TEMP_PROCESSO",
            "data_type": "FLOAT",
            "metadata": {"address": "40001"},
        },
        {
            "name": "PRESSAO_LINHA",
            "data_type": "FLOAT",
            "metadata": {"address": "40002"},
        },
        {
            "name": "ESTADO_BOMBA",
            "data_type": "BOOL",
            "metadata": {"address": "00010"},
        },
    ]


__all__ = ["generate_symbol_table"]
