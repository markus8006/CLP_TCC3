"""Simulador simples para o protocolo CIP/EtherNet-IP."""

from __future__ import annotations

from typing import Dict, List

Symbol = Dict[str, object]


def generate_symbol_tree() -> List[Symbol]:
    return [
        {
            "name": "Mixer",
            "udt_name": "MixerUDT",
            "data_type": "STRUCT",
            "children": [
                {"name": "Temperature", "data_type": "REAL", "metadata": {"address": "Mixer.Temperature"}},
                {"name": "Level", "data_type": "DINT", "metadata": {"address": "Mixer.Level"}},
            ],
        },
        {
            "name": "Conveyor",
            "data_type": "STRUCT",
            "children": [
                {
                    "name": "MotorRunning",
                    "data_type": "BOOL",
                    "metadata": {"address": "Conveyor.MotorRunning"},
                }
            ],
        },
    ]


__all__ = ["generate_symbol_tree"]
