"""Adapter que habilita leitura de dados via protocolo OPC UA."""

from __future__ import annotations

import logging
from typing import Any, Optional

try:  # pragma: no cover - opcional
    from asyncua import Client as OpcUaClient
except Exception:  # pragma: no cover - fallback sem dependência
    OpcUaClient = None  # type: ignore

from src.adapters.base_adapters import BaseAdapter
from src.simulations.runtime import simulation_registry

logger = logging.getLogger(__name__)


class OpcUaAdapter(BaseAdapter):
    """Adapter OPC UA que funciona tanto em modo real quanto simulado."""

    def __init__(self, orm: Any):
        super().__init__(orm)
        self.endpoint = getattr(
            orm,
            "endpoint",
            f"opc.tcp://{getattr(orm, 'ip_address', 'localhost')}:{getattr(orm, 'port', 4840)}",
        )
        self._client: Optional[OpcUaClient] = None

    async def connect(self) -> bool:
        if OpcUaClient is None:
            logger.warning(
                "Biblioteca asyncua indisponível; ativando modo simulado para OPC UA"
            )
            self._simulation_mode = True
            self._set_connected(True)
            return True

        if self.in_simulation():
            self._set_connected(True)
            return True

        async with self._lock:
            if self._client and self.is_connected():
                return True

            timeout_ms = getattr(self.orm, "timeout", 5000) or 5000
            self._client = OpcUaClient(
                url=self.endpoint,
                timeout=float(timeout_ms) / 1000.0,
            )
            try:
                await self._client.connect()
            except Exception:
                logger.exception("Falha ao conectar ao endpoint OPC UA %s", self.endpoint)
                self._set_connected(False)
                self._client = None
                return False

            self._set_connected(True)
            logger.info("Conectado ao servidor OPC UA em %s", self.endpoint)
            return True

    async def disconnect(self) -> None:
        if self.in_simulation():
            self._client = None
            self._set_connected(False)
            return

        async with self._lock:
            try:
                if self._client:
                    await self._client.disconnect()
            except Exception:
                logger.exception("Erro ao desconectar do servidor OPC UA %s", self.endpoint)
            finally:
                self._client = None
                self._set_connected(False)

    async def read_register(self, register_config: Any) -> Optional[Dict[str, Any]]:
        node_id = getattr(register_config, "address", None)
        if not node_id:
            logger.warning("Configuração de registrador OPC UA sem node id")
            return None

        register_id = getattr(register_config, "id", None)

        if self.in_simulation():
            simulated = simulation_registry.next_value(self.protocol_name or "opcua", register_config)
            return self._build_result(
                register_id=simulated["register_id"],
                raw_value=simulated["raw_value"],
                value_float=simulated["value_float"],
                value_int=simulated["value_int"],
                quality=simulated["quality"],
            )

        if not self._client or not self.is_connected():
            logger.debug("Leitura OPC UA sem conexão ativa")
            return None

        try:
            node = self._client.get_node(node_id)
            raw_value = await node.read_value()
        except Exception:
            logger.exception("Falha ao ler nó OPC UA %s", node_id)
            return None

        value_float = self._coerce_float(raw_value)
        value_int = self._coerce_int(raw_value)
        return self._build_result(
            register_id=register_id,
            raw_value=raw_value,
            value_float=value_float,
            value_int=value_int,
        )
