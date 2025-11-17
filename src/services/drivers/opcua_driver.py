from __future__ import annotations

import random
from typing import Dict, Iterable

from src.utils.logs import logger


class OPCUADriver:
    """Driver simplificado para conexões OPC UA."""

    def __init__(self, plc) -> None:
        self.plc = plc
        self.connected = False

    def conectar(self) -> None:
        try:
            logger.info(
                "[POLLING] Conectando OPC UA ao CLP %s (%s)",
                getattr(self.plc, "id", "?"),
                getattr(self.plc, "ip_address", ""),
            )
            self.connected = True
        except Exception:
            logger.exception("[POLLING] Falha ao conectar via OPC UA")
            self.connected = False

    def ler(self, registros: Iterable) -> Dict[str, float]:
        resultados: Dict[str, float] = {}
        try:
            for reg in registros:
                base = abs(hash((getattr(self.plc, "id", 0), reg.address))) % 75
                noise = random.gauss(0, 2)
                resultados[reg.address] = max(0.0, base + noise)
        except Exception:
            logger.exception("[POLLING] Erro ao ler registradores OPC UA")
        return resultados

    def desconectar(self) -> None:
        if not self.connected:
            return
        try:
            logger.info("[POLLING] Encerrando conexão OPC UA do CLP %s", getattr(self.plc, "id", "?"))
        except Exception:
            logger.exception("[POLLING] Erro ao desconectar OPC UA")
        finally:
            self.connected = False
