"""Descrição estruturada do suporte de protocolos e parâmetros sugeridos."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.models.PLCs import PLC


@dataclass(frozen=True)
class ProtocolField:
    """Metadados de um campo de ligação apresentado na interface."""

    name: str
    label: str
    placeholder: str
    type: str = "text"
    required: bool = False
    options: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "placeholder": self.placeholder,
            "type": self.type,
            "required": self.required,
        }
        if self.options:
            payload.update(self.options)
        return payload


@dataclass(frozen=True)
class ProtocolSupport:
    """Estrutura apresentada na página de detalhes do CLP."""

    key: str
    label: str
    support_level: str
    support_label: str
    implementation: str
    notes: Optional[str] = None
    discover_enabled: bool = True
    simulate_enabled: bool = True
    requires_file: bool = False
    fields: Iterable[ProtocolField] = field(default_factory=list)
    defaults: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "support_level": self.support_level,
            "support_label": self.support_label,
            "implementation": self.implementation,
            "notes": self.notes,
            "discover_enabled": self.discover_enabled,
            "simulate_enabled": self.simulate_enabled,
            "requires_file": self.requires_file,
            "fields": [field.as_dict() for field in self.fields],
            "defaults": self.defaults,
        }


_FULL_PROTOCOL_ALIASES = {
    "opcua": {"opcua", "opc-ua", "opcua-sim"},
    "ethernetip": {"ethernetip", "ethernet/ip", "cip"},
    "beckhoff": {"beckhoff", "beckhoff-ads", "ads"},
    "s7": {"s7", "siemens", "s7-sim"},
    "modbus": {"modbus", "modbus-tcp", "modbus-rtu", "modbus-sim"},
    "profinet": {"profinet"},
    "dnp3": {"dnp3"},
    "iec104": {"iec104", "iec-104", "iec_104"},
}


def _match_protocol(plc: Optional[PLC], key: str) -> bool:
    if plc is None or not plc.protocol:
        return False
    aliases = _FULL_PROTOCOL_ALIASES.get(key, {key})
    return plc.protocol.lower() in aliases


def _parse_rack_slot(plc: Optional[PLC]) -> Dict[str, Any]:
    if plc is None or not plc.rack_slot:
        return {}
    parts = [piece.strip() for piece in str(plc.rack_slot).replace(";", ",").split(",") if piece.strip()]
    if not parts:
        return {}
    rack = parts[0]
    slot = parts[1] if len(parts) > 1 else None
    payload: Dict[str, Any] = {}
    if rack is not None:
        payload["rack"] = rack
    if slot is not None:
        payload["slot"] = slot
    return payload


def _base_defaults(plc: Optional[PLC]) -> Dict[str, Any]:
    if plc is None:
        return {}
    payload: Dict[str, Any] = {}
    if plc.ip_address:
        payload["host"] = plc.ip_address
        payload["path"] = plc.ip_address
        payload["ip"] = plc.ip_address
        payload["endpoint"] = f"opc.tcp://{plc.ip_address}:{plc.port or 4840}"
    if plc.port:
        payload["port"] = plc.port
    if plc.unit_id is not None:
        payload["unit_id"] = plc.unit_id
    payload.update(_parse_rack_slot(plc))
    return payload


def _s7_defaults(plc: Optional[PLC]) -> Dict[str, Any]:
    defaults = _base_defaults(plc)
    if "rack" not in defaults:
        defaults["rack"] = "0"
    if "slot" not in defaults:
        defaults["slot"] = "1"
    return defaults


def _beckhoff_defaults(plc: Optional[PLC]) -> Dict[str, Any]:
    defaults = _base_defaults(plc)
    if "port" not in defaults:
        defaults["port"] = 851
    return defaults


def _ethernetip_defaults(plc: Optional[PLC]) -> Dict[str, Any]:
    defaults = _base_defaults(plc)
    if "slot" not in defaults:
        defaults["slot"] = "0"
    return defaults


def _opcua_defaults(plc: Optional[PLC]) -> Dict[str, Any]:
    defaults = _base_defaults(plc)
    if plc and plc.port:
        defaults["endpoint"] = f"opc.tcp://{plc.ip_address}:{plc.port}"
    return defaults


def get_protocol_support_matrix(plc: Optional[PLC] = None) -> List[Dict[str, Any]]:
    """Retorna a matriz de suporte com campos dinâmicos para a UI."""

    base_defaults = _base_defaults(plc)

    entries: List[ProtocolSupport] = [
        ProtocolSupport(
            key="opcua",
            label="OPC UA",
            support_level="full",
            support_label="✅ Completo",
            implementation=(
                "asyncua → usa client.get_objects_node().get_children() para navegar e montar o mapa hierárquico de tags."
            ),
            notes="Requer endpoint acessível do servidor OPC UA.",
            fields=[
                ProtocolField(
                    name="endpoint",
                    label="Endpoint OPC UA",
                    placeholder="opc.tcp://192.168.0.10:4840",
                    type="url",
                    required=True,
                ),
                ProtocolField(
                    name="timeout",
                    label="Timeout (s)",
                    placeholder="10",
                    type="number",
                    options={"min": "1", "step": "1"},
                ),
                ProtocolField(
                    name="max_nodes",
                    label="Máx. de nós",
                    placeholder="2000",
                    type="number",
                    options={"min": "10", "step": "10"},
                ),
            ],
            defaults=_opcua_defaults(plc) if _match_protocol(plc, "opcua") else base_defaults,
        ),
        ProtocolSupport(
            key="ethernetip",
            label="EtherNet/IP (Rockwell CIP)",
            support_level="full",
            support_label="✅ Completo",
            implementation="pycomm3 → LogixDriver('192.168.0.x').get_tag_list() retorna todas as tags simbólicas.",
            notes="Informe IP/path e slot quando aplicável.",
            fields=[
                ProtocolField(
                    name="path",
                    label="Endereço/Path",
                    placeholder="192.168.0.20",
                    required=True,
                ),
                ProtocolField(
                    name="slot",
                    label="Slot",
                    placeholder="0",
                    type="number",
                    options={"min": "0", "step": "1"},
                ),
            ],
            defaults=_ethernetip_defaults(plc) if _match_protocol(plc, "ethernetip") else base_defaults,
        ),
        ProtocolSupport(
            key="beckhoff",
            label="Beckhoff ADS",
            support_level="full",
            support_label="✅ Completo",
            implementation="pyads.Connection(...).get_all_symbols() exporta todas as variáveis globais do TwinCAT.",
            notes="É necessário AMS Net ID válido do controlador.",
            fields=[
                ProtocolField(
                    name="ams_net_id",
                    label="AMS Net ID",
                    placeholder="5.33.160.1.1.1",
                    required=True,
                ),
                ProtocolField(
                    name="ip",
                    label="Endereço IP",
                    placeholder="192.168.0.30",
                    required=True,
                ),
                ProtocolField(
                    name="port",
                    label="Porta",
                    placeholder="851",
                    type="number",
                    options={"min": "1", "step": "1"},
                ),
            ],
            defaults=_beckhoff_defaults(plc) if _match_protocol(plc, "beckhoff") else base_defaults,
        ),
        ProtocolSupport(
            key="s7",
            label="Siemens S7",
            support_level="partial",
            support_label="⚠️ Parcial",
            implementation=(
                "snap7 → se o servidor S7 Symbolic Access estiver habilitado, usar client.get_symbol_table() ou OPC UA alternativo."
                " Caso contrário, exigir CSV de endereçamento."
            ),
            notes="Se o acesso simbólico não estiver disponível, carregue o mapa via arquivo.",
            fields=[
                ProtocolField(
                    name="host",
                    label="Endereço IP",
                    placeholder="192.168.0.40",
                    required=True,
                ),
                ProtocolField(
                    name="rack",
                    label="Rack",
                    placeholder="0",
                    type="number",
                    required=True,
                    options={"min": "0", "step": "1"},
                ),
                ProtocolField(
                    name="slot",
                    label="Slot",
                    placeholder="1",
                    type="number",
                    required=True,
                    options={"min": "0", "step": "1"},
                ),
            ],
            defaults=_s7_defaults(plc) if _match_protocol(plc, "s7") else base_defaults,
        ),
        ProtocolSupport(
            key="modbus",
            label="Modbus TCP/RTU",
            support_level="none",
            support_label="❌ Requer mapa",
            implementation="Cria stub que lê endereços a partir de arquivo CSV/XLSX (mapa de registradores).",
            notes="Arraste o ficheiro na área de importação para carregar os registradores.",
            discover_enabled=False,
            simulate_enabled=True,
            requires_file=True,
            defaults=base_defaults,
        ),
        ProtocolSupport(
            key="profinet",
            label="Profinet",
            support_level="none",
            support_label="❌ Requer mapa",
            implementation="Acesso via índice — depende de arquivo CSV/XLSX externo.",
            notes="Utilize a importação de mapa industrial para carregar tags Profinet.",
            discover_enabled=False,
            simulate_enabled=True,
            requires_file=True,
        ),
        ProtocolSupport(
            key="dnp3",
            label="DNP3",
            support_level="none",
            support_label="❌ Requer mapa",
            implementation="Acesso via índice — também depende de arquivo CSV/XLSX externo.",
            notes="Carregue o inventário de índices via importação de mapa.",
            discover_enabled=False,
            simulate_enabled=True,
            requires_file=True,
        ),
        ProtocolSupport(
            key="iec104",
            label="IEC 60870-5-104",
            support_level="none",
            support_label="❌ Requer mapa",
            implementation="Acesso via index, portanto depende de arquivo CSV/XLSX externo.",
            notes="Utilize um mapa exportado do engenheiro IEC 104 para registrar os pontos.",
            discover_enabled=False,
            simulate_enabled=True,
            requires_file=True,
        ),
    ]

    return [entry.as_dict() for entry in entries]


__all__ = ["get_protocol_support_matrix"]
