from __future__ import annotations

import threading

from src.repository.Data_repository import DataRepo
from src.repository.Registers_repository import RegRepo
from src.services.drivers.factory import get_driver
from src.utils.logs import logger


class CLPWorker(threading.Thread):
    """Thread responsável por ler um único CLP continuamente."""

    def __init__(
        self,
        app,
        plc,
        *,
        register_repo=RegRepo,
        data_repo=DataRepo,
    ) -> None:
        super().__init__(name=f"clp-worker-{getattr(plc, 'id', 'unknown')}", daemon=True)
        self.app = app
        self.plc = plc
        self.register_repo = register_repo
        self.data_repo = data_repo
        self.intervalo = max(0.5, (getattr(plc, "polling_interval", 1000) or 1000) / 1000)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("[POLLING] Worker iniciado para CLP %s", getattr(self.plc, "id", "?"))
        driver = get_driver(self.plc)
        if driver is None:
            logger.error("[POLLING] Nenhum driver disponível para CLP %s", getattr(self.plc, "id", "?"))
            return

        with self.app.app_context():
            while not self._stop_event.is_set():
                try:
                    driver.conectar()
                    registros = self.register_repo.get_registers_for_plc(self.plc.id)
                    if not registros:
                        logger.warning("[POLLING] CLP %s sem registradores ativos.", self.plc.id)
                        self._wait_interval()
                        continue

                    valores = driver.ler(registros)
                    for reg in registros:
                        valor = valores.get(reg.address)
                        try:
                            self.data_repo.registrar_leitura(self.plc, reg, valor)
                        except Exception:
                            logger.exception(
                                "[POLLING] Falha ao salvar leitura do CLP %s registrador %s",
                                self.plc.id,
                                reg.id,
                            )
                except Exception:
                    logger.exception("[POLLING] Erro no worker do CLP %s", getattr(self.plc, "id", "?"))
                finally:
                    try:
                        driver.desconectar()
                    except Exception:
                        logger.exception("[POLLING] Erro ao desconectar CLP %s", getattr(self.plc, "id", "?"))

                self._wait_interval()

        logger.info("[POLLING] Worker finalizado para CLP %s", getattr(self.plc, "id", "?"))

    def _wait_interval(self) -> None:
        self._stop_event.wait(self.intervalo)
