"""Fornece dados simulados de descoberta de tags para fins de demonstração."""

from __future__ import annotations

from typing import Dict, List

_SIMULATED_TAGS: Dict[str, List[Dict[str, object]]] = {
    "opcua": [
        {
            "display_path": "Objects/Fábrica/Misturador/Temperatura",
            "node_id": "ns=2;s=Fabrica/Misturador/Temperatura",
            "data_type": "Double",
            "source": "opcua",
        },
        {
            "display_path": "Objects/Fábrica/Misturador/Estado",
            "node_id": "ns=2;s=Fabrica/Misturador/Estado",
            "data_type": "Boolean",
            "source": "opcua",
        },
        {
            "display_path": "Objects/Fábrica/Esteira/Velocidade",
            "node_id": "ns=2;s=Fabrica/Esteira/Velocidade",
            "data_type": "Float",
            "source": "opcua",
        },
    ],
    "ethernetip": [
        {
            "tag_name": "Mixer.Temperature",
            "data_type": "REAL",
            "dimensions": [1],
            "source": "ethernetip",
        },
        {
            "tag_name": "Mixer.Level",
            "data_type": "DINT",
            "source": "ethernetip",
        },
        {
            "tag_name": "Conveyor.MotorRunning",
            "data_type": "BOOL",
            "source": "ethernetip",
        },
    ],
    "beckhoff": [
        {
            "tag_name": "MAIN.fbPress.Pressure",
            "data_type": "REAL",
            "source": "beckhoff",
        },
        {
            "tag_name": "MAIN.fbPress.IsRunning",
            "data_type": "BOOL",
            "source": "beckhoff",
        },
        {
            "tag_name": "MAIN.fbPress.Setpoint",
            "data_type": "LREAL",
            "source": "beckhoff",
        },
    ],
    "s7": [
        {
            "tag_name": "DB1.Temperatura",
            "address": "DB1.DBW0",
            "data_type": "REAL",
            "source": "s7",
        },
        {
            "tag_name": "DB1.Nivel",
            "address": "DB1.DBW4",
            "data_type": "REAL",
            "source": "s7",
        },
        {
            "tag_name": "DB1.BombaAtiva",
            "address": "DB1.DBX8.0",
            "data_type": "BOOL",
            "source": "s7",
        },
    ],
    "modbus": [
        {
            "tag_name": "TEMP_PROCESSO",
            "address": "40001",
            "data_type": "FLOAT",
            "description": "Temperatura do forno",
            "source": "modbus",
        },
        {
            "tag_name": "PRESSAO_LINHA",
            "address": "40002",
            "data_type": "FLOAT",
            "description": "Pressão em bar",
            "source": "modbus",
        },
        {
            "tag_name": "ESTADO_BOMBA",
            "address": "00010",
            "data_type": "BOOL",
            "description": "Contato auxiliar bomba",
            "source": "modbus",
        },
    ],
    "profinet": [
        {
            "tag_name": "AI_Temperatura",
            "index": 16,
            "subindex": 1,
            "data_type": "REAL",
            "description": "Entrada analógica módulo 1",
            "source": "profinet",
        },
        {
            "tag_name": "DI_Emergencia",
            "index": 32,
            "subindex": 2,
            "data_type": "BOOL",
            "description": "Botão de emergência",
            "source": "profinet",
        },
    ],
    "dnp3": [
        {
            "tag_name": "AI_Subestacao_1",
            "group": 30,
            "variation": 1,
            "index": 12,
            "description": "Medidor de tensão",
            "source": "dnp3",
        },
        {
            "tag_name": "DI_Subestacao_1",
            "group": 1,
            "variation": 2,
            "index": 5,
            "description": "Estado disjuntor",
            "source": "dnp3",
        },
    ],
    "iec104": [
        {
            "tag_name": "TI.1.101",
            "index": 101,
            "data_type": "FLOAT",
            "description": "Temperatura transformador",
            "source": "iec104",
        },
        {
            "tag_name": "SP.1.16",
            "index": 16,
            "data_type": "BOOL",
            "description": "Sinalização proteção",
            "source": "iec104",
        },
    ],
}

_ALIASES = {
    "opc-ua": "opcua",
    "opcua-sim": "opcua",
    "ethernet/ip": "ethernetip",
    "cip": "ethernetip",
    "beckhoff-ads": "beckhoff",
    "ads": "beckhoff",
    "siemens": "s7",
    "s7-sim": "s7",
    "modbus-rtu": "modbus",
    "modbus-tcp": "modbus",
    "modbus-sim": "modbus",
}


def get_simulated_tags(protocol: str) -> List[Dict[str, object]]:
    """Retorna a lista simulada associada ao protocolo informado."""

    if not protocol:
        raise ValueError("Informe o protocolo a ser simulado.")
    key = protocol.lower()
    key = _ALIASES.get(key, key)
    try:
        return _SIMULATED_TAGS[key]
    except KeyError as exc:
        raise ValueError(f"Protocolo {protocol!r} não possui simulador configurado.") from exc


__all__ = ["get_simulated_tags"]
