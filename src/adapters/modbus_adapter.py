import asyncio
from pymodbus.client import AsyncModbusTcpClient
import logging
from typing import List, Dict, Optional, Any
from src.repository.PLC_repository import Plcrepo  # ajuste se necessário

logger = logging.getLogger(__name__)

class ModbusAdapter:
    def __init__(self, orm):
        self.orm = orm
        self.ip_address = getattr(self.orm, "ip_address", None)
        self.port = getattr(self.orm, "port", 502)
        self.timeout = getattr(self.orm, "timeout", 3)
        self.client: Optional[AsyncModbusTcpClient] = None
        self._connected: bool = False

    async def connect(self) -> bool:
        """Conecta ao PLC (async)."""
        try:
            self.client = AsyncModbusTcpClient(host=self.ip_address, port=self.port, timeout=self.timeout)
            await self.client.connect()
            # alguns clients definem .connected
            self._connected = getattr(self.client, "connected", True)
            if self._connected:
                logger.info("Conectado ao PLC %s:%s", self.ip_address, self.port)
                # Atualizar ORM e persistir via repo — ajuste Plcrepo.update conforme sua implementação
                try:
                    self.orm.is_online = True
                    # Se Plcrepo.update for método de classe/estático que aceita instância:
                    Plcrepo.update(self.orm)
                except Exception:
                    # Se seu repo precisar ser instanciado com db/session, faça isso no seu código real
                    logger.debug("Não foi possível atualizar Plcrepo automaticamente (verifique a API do repo).")
            return self._connected
        except Exception as e:
            logger.exception("Erro ao conectar PLC %s: %s", self.ip_address, self.port, e)
            self._connected = False
            return False

    async def disconnect(self):
        """Desconecta do PLC (async)."""
        try:
            if self.client:
                close_fn = getattr(self.client, "close", None)
                if asyncio.iscoroutinefunction(close_fn):
                    await close_fn()
                elif callable(close_fn):
                    close_fn()
            self._connected = False
            logger.info("Desconectado do PLC %s:%s", self.ip_address, self.port)
            self.orm.is_online = False
            try:
                Plcrepo.update(self.orm)
            except Exception:
                logger.debug("Não foi possível atualizar Plcrepo na desconexão.")
        except Exception:
            logger.exception("Erro ao desconectar do PLC %s", self.ip_address)

    async def read_register(self, register_config: Any) -> Optional[Dict]:
        """Lê um único registrador (async)."""
        if not self._connected or self.client is None:
            logger.debug("Tentativa de leitura sem conexão.")
            return None

        try:
            addr = int(getattr(register_config, "address", 0))
            reg_type = getattr(register_config, 'register_type', 'holding')
            slave = int(getattr(register_config, "slave", 1))

            if reg_type == 'holding':
                print(slave)
                resp = await self.client.read_holding_registers(addr, count=1, slave=slave)
            elif reg_type == 'input':
                resp = await self.client.read_input_registers(addr, 1, slave=slave)
            elif reg_type == 'coil':
                resp = await self.client.read_coils(addr, 1, slave=slave)
            else:
                logger.warning("Tipo de registrador desconhecido: %s", reg_type)
                return None
            

            if hasattr(resp, "isError") and resp.isError():
                logger.warning("Resposta com erro do PLC: %s", resp)
                return None

            # extrair raw
            if hasattr(resp, "registers") and resp.registers:
                raw_value = resp.registers[0]
            elif hasattr(resp, "bits") and resp.bits:
                raw_value = int(resp.bits[0])
            else:
                raw_value = None

            converted_value = self._convert_value(raw_value, getattr(register_config, 'data_type', 'int16'))

            return {
                'register_id': getattr(register_config, 'id'),
                'raw_value': raw_value,
                'converted_value': converted_value,
                'quality': 'good' if raw_value is not None else 'bad',
                'timestamp': asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.exception("Erro ao ler registrador %s: %s", register_config, e)
            return None

    def _convert_value(self, raw_value: int, data_type: str) -> Optional[float]:
        if raw_value is None:
            return None
        try:
            if data_type == 'int16':
                return raw_value - 65536 if raw_value > 32767 else raw_value
            if data_type == 'uint16':
                return float(raw_value)
            if data_type == 'bool':
                return float(bool(raw_value))
            return float(raw_value)
        except Exception:
            return None

    def is_connected(self) -> bool:
        return self._connected and (self.client is not None)
