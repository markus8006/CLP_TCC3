from __future__ import annotations

import random
from typing import Dict, Iterable

from src.utils.logs import logger


class S7Driver:
    """Driver simplificado para CLPs Siemens S7."""

    def __init__(self, plc) -> None:
        self.plc = plc
        self.connected = False

    def conectar(self) -> None:
        try:
            logger.info(
                "[POLLING] Conectando S7 ao CLP %s (rack/slot=%s)",
                getattr(self.plc, "id", "?"),
                getattr(self.plc, "rack_slot", ""),
            )
            self.connected = True
        except Exception:
            logger.exception("[POLLING] Falha ao conectar via S7")
            self.connected = False

    def ler(self, registros: Iterable) -> Dict[str, float]:
        resultados: Dict[str, float] = {}
        try:
            for reg in registros:
                base = abs(hash((getattr(self.plc, "id", 0), reg.address))) % 50
                resultados[reg.address] = base + random.random()
        except Exception:
            logger.exception("[POLLING] Erro ao ler registradores S7")
        return resultados

    def desconectar(self) -> None:
        if not self.connected:
            return
        try:
            logger.info("[POLLING] Encerrando conexão S7 do CLP %s", getattr(self.plc, "id", "?"))
        except Exception:
            logger.exception("[POLLING] Erro ao desconectar S7")
        finally:
            self.connected = False
