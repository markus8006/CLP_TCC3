"""Simulador mínimo para o driver Beckhoff ADS."""

from __future__ import annotations

from typing import Dict, List

Symbol = Dict[str, object]


def generate_symbol_tree() -> List[Symbol]:
    return [
        {
            "name": "MAIN",
            "data_type": "PROGRAM",
            "children": [
                {
                    "name": "fbPress",
                    "data_type": "FUNCTION_BLOCK",
                    "children": [
                        {
                            "name": "Pressure",
                            "data_type": "REAL",
                            "metadata": {"address": "MAIN.fbPress.Pressure"},
                        },
                        {
                            "name": "IsRunning",
                            "data_type": "BOOL",
                            "metadata": {"address": "MAIN.fbPress.IsRunning"},
                        },
                        {
                            "name": "Setpoint",
                            "data_type": "LREAL",
                            "metadata": {"address": "MAIN.fbPress.Setpoint"},
                        },
                    ],
                }
            ],
        }
    ]


__all__ = ["generate_symbol_tree"]
