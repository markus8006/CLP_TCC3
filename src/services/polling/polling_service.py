from __future__ import annotations

import threading
from typing import Dict, Optional

from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Data_repository import DataRepo
from src.services.polling.clp_worker import CLPWorker
from src.services.settings_service import get_polling_enabled
from src.utils.logs import logger


class PollingService:
    """Serviço simples que inicia um worker por CLP."""

    def __init__(
        self,
        app,
        *,
        plc_repo=Plcrepo,
        register_repo=RegRepo,
        data_repo=DataRepo,
    ) -> None:
        self.app = app
        self.plc_repo = plc_repo
        self.register_repo = register_repo
        self.data_repo = data_repo
        self._workers: Dict[int, CLPWorker] = {}
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            if not get_polling_enabled(default=True):
                logger.info("[POLLING] Serviço desativado nas configurações. Não iniciando threads.")
                return
            logger.info("[POLLING] Iniciando PollingService")
            with self.app.app_context():
                plcs = self.plc_repo.list_all()
            if not plcs:
                logger.info("[POLLING] Nenhum CLP encontrado. PollingService permanecerá parado.")
                return
            for plc in plcs:
                worker = CLPWorker(
                    self.app,
                    plc,
                    register_repo=self.register_repo,
                    data_repo=self.data_repo,
                )
                logger.info("[POLLING] Iniciando worker para CLP %s", getattr(plc, "id", "?"))
                self._workers[plc.id] = worker
                worker.start()
            self._running = True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            logger.info("[POLLING] Encerrando PollingService")
            for worker in list(self._workers.values()):
                worker.stop()
            for worker in list(self._workers.values()):
                worker.join(timeout=5)
            self._workers.clear()
            self._running = False

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    @property
    def is_running(self) -> bool:
        return self._running


def register_polling(app) -> Optional[PollingService]:
    try:
        service = PollingService(app)
        app.extensions["polling"] = service
        service.start()
        return service
    except Exception:
        logger.exception("[POLLING] Falha ao iniciar o PollingService")
        return None
