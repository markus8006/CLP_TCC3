"""Adapter para comunicação com CLPs Siemens via protocolo S7."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Optional, Tuple

try:  # pragma: no cover - dependência opcional
    import snap7
    from snap7.util import get_bool, get_dint, get_int, get_real
    from snap7.types import Areas
except Exception:  # pragma: no cover - fallback quando snap7 não está disponível
    snap7 = None  # type: ignore
    Areas = None  # type: ignore
    get_bool = get_dint = get_int = get_real = None  # type: ignore

from src.adapters.base_adapters import BaseAdapter

logger = logging.getLogger(__name__)

_DB_ADDRESS_RE = re.compile(
    r"DB(?P<db>\d+)\.DB(?P<type>[XBWD])(?P<start>\d+)(?:\.(?P<bit>\d+))?",
    re.IGNORECASE,
)
_M_ADDRESS_RE = re.compile(
    r"M(?P<start>\d+)(?:\.(?P<bit>\d+))?",
    re.IGNORECASE,
)


class S7Adapter(BaseAdapter):
    """Adapter para CLPs S7 com suporte a modo simulado para testes."""

    def __init__(self, orm: Any):
        super().__init__(orm)
        self.ip_address = getattr(orm, "ip_address", None)
        self.port = getattr(orm, "port", 102)
        self.rack_slot = getattr(orm, "rack_slot", "0,2")
        self._client: Optional["snap7.client.Client"] = None
        self._mock_mode = False
        self._mock_values: Dict[str, float] = {}

    async def connect(self) -> bool:
        if snap7 is None:
            logger.warning("Biblioteca snap7 indisponível; ativando modo simulado para S7")
            self._mock_mode = True
            self._set_connected(True)
            return True

        async with self._lock:
            if self._client and self.is_connected():
                return True

            self._client = snap7.client.Client()
            rack, slot = self._parse_rack_slot(self.rack_slot)
            try:
                await asyncio.to_thread(
                    self._client.connect,
                    self.ip_address,
                    rack,
                    slot,
                    self.port,
                )
            except Exception:
                logger.exception(
                    "Falha ao conectar ao PLC S7 %s (rack=%s slot=%s)",
                    self.ip_address,
                    rack,
                    slot,
                )
                self._client = None
                self._set_connected(False)
                return False

            connected = await asyncio.to_thread(self._client.get_connected)
            self._set_connected(bool(connected))
            if self.is_connected():
                logger.info("Conectado ao PLC S7 %s", self.ip_address)
            return self.is_connected()

    async def disconnect(self) -> None:
        async with self._lock:
            try:
                if self._client:
                    await asyncio.to_thread(self._client.disconnect)
            except Exception:
                logger.exception("Erro ao desconectar do PLC S7 %s", self.ip_address)
            finally:
                self._client = None
                self._set_connected(False)
                self._mock_mode = False
                self._mock_values.clear()

    async def read_register(self, register_config: Any) -> Optional[Dict[str, Any]]:
        address = getattr(register_config, "address", "")
        if not address:
            logger.warning("Registrador S7 sem endereço configurado")
            return None

        register_id = getattr(register_config, "id", None)
        data_type = str(getattr(register_config, "data_type", "")) or "int"

        if self._mock_mode:
            raw_value = self._mock_values.get(address)
            if raw_value is None:
                raw_value = float(len(self._mock_values) + 1)
                self._mock_values[address] = raw_value
            return self._build_result(
                register_id=register_id,
                raw_value=raw_value,
                value_float=float(raw_value),
                value_int=int(raw_value),
            )

        if not self._client or not self.is_connected():
            logger.debug("Leitura S7 sem conexão ativa")
            return None

        decoded = self._decode_address(address)
        if not decoded:
            logger.warning("Endereço S7 não reconhecido: %s", address)
            return None

        try:
            raw_value = await self._read_from_plc(decoded, data_type)
        except Exception:
            logger.exception("Erro ao ler endereço S7 %s", address)
            return None

        value_float = self._coerce_float(raw_value)
        value_int = self._coerce_int(raw_value)
        return self._build_result(
            register_id=register_id,
            raw_value=raw_value,
            value_float=value_float,
            value_int=value_int,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_rack_slot(self, value: Any) -> Tuple[int, int]:
        if isinstance(value, str):
            parts = re.split(r"[.,;/\\s]+", value.strip())
            if len(parts) >= 2:
                try:
                    return int(parts[0]), int(parts[1])
                except ValueError:
                    pass
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            try:
                return int(value[0]), int(value[1])
            except (TypeError, ValueError):
                pass
        return 0, 2

    def _decode_address(self, address: str):
        match = _DB_ADDRESS_RE.fullmatch(address)
        if match:
            return {
                "area": "DB",
                "db": int(match.group("db")),
                "type": match.group("type").upper(),
                "start": int(match.group("start")),
                "bit": int(match.group("bit")) if match.group("bit") else None,
            }
        match = _M_ADDRESS_RE.fullmatch(address)
        if match:
            return {
                "area": "M",
                "start": int(match.group("start")),
                "bit": int(match.group("bit")) if match.group("bit") else None,
            }
        return None

    async def _read_from_plc(self, decoded: Dict[str, Any], data_type: str):
        if Areas is None or snap7 is None:
            raise RuntimeError("Biblioteca snap7 indisponível")

        area = decoded["area"]
        if area == "DB":
            db = decoded["db"]
            start = decoded["start"]
            size = self._resolve_size(data_type)
            data = await asyncio.to_thread(self._client.db_read, db, start, size)
            return self._decode_value(data, decoded.get("type"), decoded.get("bit"), data_type)
        if area == "M":
            start = decoded["start"]
            size = self._resolve_size(data_type)
            data = await asyncio.to_thread(
                self._client.read_area,
                Areas.MK,
                0,
                start,
                size,
            )
            return self._decode_value(data, None, decoded.get("bit"), data_type)
        raise ValueError(f"Área S7 desconhecida: {area}")

    def _resolve_size(self, data_type: str) -> int:
        mapping = {
            "bool": 1,
            "byte": 1,
            "int": 2,
            "int16": 2,
            "uint16": 2,
            "word": 2,
            "dint": 4,
            "int32": 4,
            "real": 4,
            "float": 4,
            "dword": 4,
        }
        return mapping.get(data_type.lower(), 4)

    def _decode_value(self, data: bytes, area_type: Optional[str], bit: Optional[int], data_type: str):
        dtype = data_type.lower()
        if dtype in {"bool"} and get_bool:
            return get_bool(data, 0, bit or 0)
        if dtype in {"int", "int16"} and get_int:
            return get_int(data, 0)
        if dtype in {"dint", "int32"} and get_dint:
            return get_dint(data, 0)
        if dtype in {"real", "float"} and get_real:
            return get_real(data, 0)
        if dtype in {"uint16", "word"}:
            return int.from_bytes(data[:2], byteorder="big", signed=False)
        if dtype in {"dword"}:
            return int.from_bytes(data[:4], byteorder="big", signed=False)

        # Quando não há correspondência direta, tentar inferir pelo tipo da área
        if area_type == "X" and get_bool:
            return get_bool(data, 0, bit or 0)
        if area_type == "W" and get_int:
            return get_int(data, 0)
        if area_type == "D" and get_dint:
            return get_dint(data, 0)
        return int.from_bytes(data, byteorder="big", signed=False)
