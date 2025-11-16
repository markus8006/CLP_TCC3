"""Servidor OPC UA simulado para scraping de símbolos."""

from __future__ import annotations

from typing import Dict, List

Symbol = Dict[str, object]


def generate_symbol_tree() -> List[Symbol]:
    base = "Objects/Fábrica"
    return [
        {
            "name": "Misturador",
            "path": f"{base}/Misturador",
            "display_path": f"{base}/Misturador",
            "children": [
                {
                    "name": "Temperatura",
                    "path": f"{base}/Misturador/Temperatura",
                    "display_path": f"{base}/Misturador/Temperatura",
                    "node_id": "ns=2;s=Fabrica/Misturador/Temperatura",
                    "data_type": "Double",
                },
                {
                    "name": "Estado",
                    "path": f"{base}/Misturador/Estado",
                    "display_path": f"{base}/Misturador/Estado",
                    "node_id": "ns=2;s=Fabrica/Misturador/Estado",
                    "data_type": "Boolean",
                },
            ],
        },
        {
            "name": "Esteira",
            "path": f"{base}/Esteira",
            "display_path": f"{base}/Esteira",
            "children": [
                {
                    "name": "Velocidade",
                    "path": f"{base}/Esteira/Velocidade",
                    "display_path": f"{base}/Esteira/Velocidade",
                    "node_id": "ns=2;s=Fabrica/Esteira/Velocidade",
                    "data_type": "Float",
                }
            ],
        },
    ]


__all__ = ["generate_symbol_tree"]
