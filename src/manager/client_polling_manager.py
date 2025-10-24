# src/manager/client_polling_manager.py
import asyncio
import time
import socket
from typing import Dict, Any, Optional, List
from src.utils.logs import logger
from src.adapters.modbus_adapter import ModbusAdapter
from src.models.PLCs import PLC

from concurrent.futures import ThreadPoolExecutor

from src.services.Alarms_service import AlarmService
from src.repository.Data_repository import DataRepo



# ---------- util: espera porta tcp abrir ----------
def wait_for_port(host: str, port: int, timeout: float = 8.0, interval: float = 0.2) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except Exception:
            time.sleep(interval)
    return False


# ---------- Active client (async) que mantém uma conexão por PLC ----------
class ActivePLCPoller:
    def __init__(self, plc_orm: PLC, registers_provider: Any, flask_app):
        """
        plc_orm: PLC SQLAlchemy object
        registers_provider: callable (sync or async) -> list of register dicts
        """
        self.plc_orm = plc_orm
        self.registers_provider = registers_provider
        self.adapter = ModbusAdapter(plc_orm)
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._backoff = 1.0
        self.context = flask_app

        self.alarm_service = AlarmService()
        self.datalog_repo = DataRepo
        # executor para operações bloqueantes com DB
        self._executor = ThreadPoolExecutor(max_workers=2)


    def _process_batch_sync(self, batch: List[Dict[str, Any]]):
        """
        Para cada item do batch:
         - chama AlarmService.check_and_handle(plc_id, register_id, value)
         - marca rec['is_alarm'] se check_and_handle retornar True
        Depois faz bulk_insert no DataLogRepo.
        IMPORTANTE: essa função é síncrona e deve rodar em executor para não bloquear o loop.
        """
        # note: alarm_service e datalog_repo usam sessões síncronas (Flask-SQLAlchemy).
        with self.context.app_context():
            try:
                for rec in batch:
                    plc_id = rec.get('plc_id')
                    register_id = rec.get('register_id')
                    value = rec.get('value_float')
                    try:
                    # check_and_handle retorna True se disparou alarme
                        triggered = self.alarm_service.check_and_handle(plc_id, register_id, value)
                        if triggered:
                            rec['is_alarm'] = True
                    except Exception:
                    # garantir que uma exceção em um registro não pare o resto
                        logger.exception("Erro em AlarmService para plc=%s reg=%s", plc_id, register_id)

            # após processar os alarms, insere tudo em lote
                try:
                # adapte para os campos que seu DataLogRepo espera
                    self.datalog_repo.bulk_insert(batch)
                except Exception:
                    logger.exception("Erro ao inserir batch de DataLog")
            except Exception:
                logger.exception("Erro geral em _process_batch_sync")

    def _key(self) -> str:
        return f"{self.plc_orm.ip_address}|{self.plc_orm.vlan_id or 0}"

    async def start(self):
        self._stop = False
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._stop = True
        if self._task:
            self._task.cancel()
            await asyncio.sleep(0) # allow task to cancel
            self._task = None

    async def _run_loop(self):
        logger.info(f"PLCPoller starting for {self._key()}")

        while not self._stop:
            try:
                if not self.adapter.is_connected():
                    connected = await self.adapter.connect()
                    if not connected:
                        logger.warning(f"Unable to connect to {self._key()} -- retrying in {self._backoff:.1f}s")
                        await asyncio.sleep(self._backoff)
                        self._backoff = min(self._backoff * 2, 30.0)
                        continue
                    self._backoff = 1.0 # Reset backoff on successful connection

                 # Read registers -> montar batch de registros prontos para o DB

                 # Get registers
                if asyncio.iscoroutinefunction(self.registers_provider):
                    regs = await self.registers_provider()
                else:
                    regs = self.registers_provider()

                if not regs:
                    logger.debug(f"No registers for plc {self._key()}")
                    await asyncio.sleep(1)
                    continue
                
                results_batch = []
                for r in regs:
                    read_result = await self.adapter.read_register(r)

                    if read_result:
                        rec = {
                            'plc_id': read_result.get('plc_id') or getattr(self.plc_orm, 'id', None),
                            'register_id': read_result.get('register_id'),
                            'timestamp': read_result.get('timestamp'),
                            'raw_value': str(read_result.get('raw_value')),
                            'value_float': read_result.get('value_float'),
                            'value_int': read_result.get('value_int', None),
                            'quality': read_result.get('quality'),
                            'unit': getattr(r, 'unit', None),
                            'tags': getattr(r, 'tags', None),
                            'is_alarm': False,
                        }
                        results_batch.append(rec)

                # Se houver leituras, processe o batch **uma única vez** no executor
                if results_batch:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._executor, self._process_batch_sync, results_batch)


                await asyncio.sleep(1) # Polling interval

            except asyncio.CancelledError:
                logger.info(f"Polling loop for {self._key()} was cancelled.")
                break
            except Exception as e:
                logger.exception(f"Unexpected error in poll loop for {self._key()}: {e}")
                await self.adapter.disconnect()
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)

        await self.adapter.disconnect()
        logger.info(f"PLCPoller stopped for {self._key()}")


# ---------- Simple manager that keeps pollers by key (ip|vlan) ----------
class SimpleManager:
    def __init__(self, flask_app):
        self._pollers: Dict[str, ActivePLCPoller] = {}
        self._lock = asyncio.Lock()
        self.flask_app = flask_app

    @staticmethod
    def make_key(ip: str, vlan: Optional[int]) -> str:
        return f"{ip}|{vlan or 0}"

    async def add_plc(self, plc_orm: PLC, registers_provider):
        key = self.make_key(plc_orm.ip_address, plc_orm.vlan_id)
        async with self._lock:
            if key in self._pollers:
                logger.info(f"PLC already managed: {key}")
                return self._pollers[key]
            poller = ActivePLCPoller(plc_orm, registers_provider, flask_app=self.flask_app)
            self._pollers[key] = poller
            await poller.start()
            logger.info(f"Added plc poller {key}")
            return poller

    async def remove_plc(self, ip: str, vlan: Optional[int] = None):
        key = self.make_key(ip, vlan)
        async with self._lock:
            p = self._pollers.pop(key, None)
        if p:
            await p.stop()
            logger.info(f"Removed plc poller {key}")
            return True
        return False

    async def shutdown(self):
        async with self._lock:
            pollers = list(self._pollers.values())
            self._pollers.clear()
        tasks = [p.stop() for p in pollers]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Manager shutdown complete")
