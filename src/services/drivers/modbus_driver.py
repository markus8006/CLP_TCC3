from __future__ import annotations

import random
from typing import Dict, Iterable

from src.utils.logs import logger


class ModbusDriver:
    """Driver simplificado para leituras Modbus."""

    def __init__(self, plc) -> None:
        self.plc = plc
        self.connected = False

    def conectar(self) -> None:
        try:
            logger.info(
                "[POLLING] Conectando Modbus ao CLP %s (%s:%s)",
                getattr(self.plc, "id", "?"),
                getattr(self.plc, "ip_address", ""),
                getattr(self.plc, "port", ""),
            )
            self.connected = True
        except Exception:
            logger.exception("[POLLING] Falha ao conectar via Modbus")
            self.connected = False

    def ler(self, registros: Iterable) -> Dict[str, float]:
        resultados: Dict[str, float] = {}
        try:
            for reg in registros:
                base = abs(hash((getattr(self.plc, "id", 0), reg.address))) % 100
                resultados[reg.address] = base + random.random()
        except Exception:
            logger.exception("[POLLING] Erro ao ler registradores Modbus")
        return resultados

    def desconectar(self) -> None:
        if not self.connected:
            return
        try:
            logger.info("[POLLING] Encerrando conexão Modbus do CLP %s", getattr(self.plc, "id", "?"))
        except Exception:
            logger.exception("[POLLING] Erro ao desconectar Modbus")
        finally:
            self.connected = False
