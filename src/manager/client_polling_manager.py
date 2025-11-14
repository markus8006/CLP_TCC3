import asyncio
import time
import socket
from typing import Dict, Any, Optional, List
from src.utils.logs import logger
from src.adapters.factory import get_adapter
from src.models.PLCs import PLC
from concurrent.futures import ThreadPoolExecutor
from src.services.Alarms_service import AlarmService
from src.repository.Data_repository import DataRepo
from src.repository.PLC_repository import Plcrepo
import os
import inspect
from datetime import datetime, timezone
from src.services.mqtt_service import get_mqtt_publisher
from src.app.settings import AppSettings, get_app_settings

# número máximo de threads
max_workers = min(32, (os.cpu_count() or 4) * 4)


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
    def __init__(
        self,
        plc_orm: PLC,
        registers_provider: Any,
        flask_app,
        *,
        settings: Optional[AppSettings] = None,
    ):
        """
        plc_orm: PLC SQLAlchemy object
        registers_provider: callable (sync or async) -> list of register dicts/objects
        """
        self.plc_orm = plc_orm
        self.registers_provider = registers_provider
        self._settings = settings or get_app_settings(flask_app)
        protocol = getattr(plc_orm, 'protocol', 'modbus')
        try:
            self.adapter = get_adapter(protocol, plc_orm, settings=self._settings)
        except ValueError:
            logger.warning(
                "Protocolo %s não suportado para o PLC %s; usando Modbus como fallback",
                protocol,
                getattr(plc_orm, 'id', '<desconhecido>'),
            )
            self.adapter = get_adapter('modbus', plc_orm, settings=self._settings)
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._backoff = 1.0
        self.context = flask_app
        self._polling_allowed = self._settings.features.enable_polling and not (
            self._settings.demo.enabled and self._settings.demo.disable_polling
        )

        self.alarm_service = AlarmService()
        self.datalog_repo = DataRepo
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._mqtt = get_mqtt_publisher()

        # detecta se adapter.read_register é coroutinefunction
        self._read_is_coroutine = inspect.iscoroutinefunction(getattr(self.adapter, "read_register", None))
        self._reported_online = False
        self._last_seen_update: Optional[datetime] = None

        try:
            if hasattr(self.plc_orm, "tags_as_list"):
                self._plc_tags = self.plc_orm.tags_as_list()
            else:
                self._plc_tags = getattr(self.plc_orm, "tags", None)
        except Exception:
            logger.exception("Falha ao obter tags do PLC %s", self._key())
            self._plc_tags = None

    def _update_plc_state(self, *, online: bool, update_last_seen: bool = False) -> None:
        try:
            with self.context.app_context():
                plc = Plcrepo.get(self.plc_orm.id)
                if not plc:
                    return

                now = datetime.now(timezone.utc)
                changed = False

                if plc.is_online != online:
                    plc.is_online = online
                    plc.status_changed_at = now
                    if not online:
                        plc.last_seen = None
                    changed = True

                if online and update_last_seen:
                    last_seen = plc.last_seen
                    if last_seen and last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                    if not last_seen or now > last_seen:
                        plc.last_seen = now
                        changed = True

                if changed:
                    Plcrepo.update(plc)
                    self.plc_orm.is_online = plc.is_online
                    self.plc_orm.last_seen = plc.last_seen
        except Exception:
            logger.exception("Falha ao actualizar estado online/offline do PLC %s", self._key())

    def _mark_online(self, *, update_last_seen: bool = False) -> None:
        was_offline = not self._reported_online
        self._update_plc_state(online=True, update_last_seen=update_last_seen)
        self._reported_online = True
        if update_last_seen:
            self._last_seen_update = datetime.now(timezone.utc)
        if was_offline:
            try:
                self._mqtt.publish_connectivity_event(self.plc_orm, "ONLINE")
            except Exception:
                logger.exception("Erro ao publicar evento de conectividade ONLINE para %s", self._key())

    def _mark_offline(self) -> None:
        if self._reported_online:
            self._update_plc_state(online=False)
            self._reported_online = False
            try:
                self._mqtt.publish_connectivity_event(self.plc_orm, "OFFLINE")
            except Exception:
                logger.exception("Erro ao publicar evento de conectividade OFFLINE para %s", self._key())
        self._last_seen_update = None

    def _touch_last_seen(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_seen_update and (now - self._last_seen_update).total_seconds() < 5:
            return
        self._mark_online(update_last_seen=True)

    def _process_batch_sync(self, batch: List[Dict[str, Any]]):
        """
        Para cada item do batch:
         - chama AlarmService.check_and_handle(plc_id, register_id, value)
         - marca rec['is_alarm'] se check_and_handle retornar True
        Depois faz bulk_insert no DataLogRepo.
        """
        with self.context.app_context():
            publish_payloads: List[Dict[str, Any]] = []
            try:
                for rec in batch:
                    meta = rec.pop('_publish_meta', None)
                    plc_id = rec.get('plc_id')
                    register_id = rec.get('register_id')
                    value = rec.get('value_float')
                    try:
                        triggered = self.alarm_service.check_and_handle(plc_id, register_id, value)
                        if triggered:
                            rec['is_alarm'] = True
                            if meta is not None:
                                meta['is_alarm'] = True
                    except Exception:
                        logger.exception("Erro em AlarmService para plc=%s reg=%s", plc_id, register_id)
                    if meta is not None:
                        publish_payloads.append(meta)

                try:
                    self.datalog_repo.bulk_insert(batch)
                except Exception:
                    logger.exception("Erro ao inserir batch de DataLog")

                if publish_payloads:
                    try:
                        self._mqtt.publish_measurements(publish_payloads)
                    except Exception:
                        logger.exception("Erro ao publicar medições no MQTT")
            except Exception:
                logger.exception("Erro geral em _process_batch_sync")

    def _key(self) -> str:
        return f"{self.plc_orm.ip_address}|{self.plc_orm.vlan_id or 0}"

    def _call_registers_provider(self):
        provider = self.registers_provider
        if asyncio.iscoroutinefunction(provider):
            return provider()
        try:
            if self.context:
                with self.context.app_context():
                    return provider()
            return provider()
        except RuntimeError:
            return provider()

    async def _disconnect_adapter(self) -> None:
        try:
            await self.adapter.disconnect()
        except Exception:
            logger.exception("Falha ao desconectar adapter após erro.")

    async def poll_once(self, *, sleep: bool = True) -> None:
        try:
            if not self.adapter.is_connected():
                connected = await self.adapter.connect()
                if not connected:
                    logger.warning(
                        "Unable to connect to %s -- retrying in %.1fs",
                        self._key(),
                        self._backoff,
                    )
                    self._mark_offline()
                    if sleep:
                        await asyncio.sleep(self._backoff)
                    self._backoff = min(self._backoff * 2, 30.0)
                    return
                self._backoff = 1.0
                self._mark_online(update_last_seen=True)

            regs_result = self._call_registers_provider()
            regs = await regs_result if asyncio.iscoroutine(regs_result) else regs_result
            if not regs:
                logger.debug("No registers for plc %s", self._key())
                if sleep:
                    await asyncio.sleep(1)
                return

            loop = asyncio.get_event_loop()
            results_batch = []
            tasks: List[asyncio.Task] = []
            task_to_reg: Dict[asyncio.Task, Any] = {}

            max_concurrent_reads = min(16, len(regs))
            sem = asyncio.Semaphore(max_concurrent_reads)

            async def read_register_concurrent(register):
                async with sem:
                    try:
                        if self._read_is_coroutine:
                            return await self.adapter.read_register(register)
                        return await loop.run_in_executor(self._executor, self.adapter.read_register, register)
                    except Exception as e:
                        logger.error(
                            "Erro lendo %s @ %s:%s",
                            getattr(register, 'id', register),
                            getattr(register, 'address', ''),
                            e,
                        )
                        return None

            for r in regs:
                t = asyncio.create_task(read_register_concurrent(r))
                tasks.append(t)
                task_to_reg[t] = r

            for fut in asyncio.as_completed(tasks):
                try:
                    read_result = await fut
                except Exception as e:
                    logger.error("Task de leitura falhou: %s", e)
                    continue

                reg_for_task = task_to_reg.get(fut)
                if not read_result:
                    continue

                if asyncio.iscoroutine(read_result):
                    try:
                        read_result = await read_result
                    except Exception as e:
                        logger.error("Coroutine read_result falhou ao await: %s", e)
                        continue

                try:
                    plc_id = read_result.get('plc_id') or getattr(self.plc_orm, 'id', None)
                    register_id = read_result.get('register_id')
                    timestamp = read_result.get('timestamp')
                    unit = getattr(reg_for_task, 'unit', None)
                    rec = {
                        'plc_id': plc_id,
                        'register_id': register_id,
                        'timestamp': timestamp,
                        'raw_value': str(read_result.get('raw_value')),
                        'value_float': read_result.get('value_float'),
                        'value_int': read_result.get('value_int', None),
                        'quality': read_result.get('quality'),
                        'unit': unit,
                        'tags': getattr(reg_for_task, 'tags', None),
                        'is_alarm': False,
                        '_publish_meta': {
                            'plc_id': plc_id,
                            'plc_name': getattr(self.plc_orm, 'name', None),
                            'protocol': getattr(self.plc_orm, 'protocol', None),
                            'plc_tags': self._plc_tags,
                            'register_id': register_id,
                            'register_name': getattr(reg_for_task, 'name', None),
                            'register_tag': getattr(reg_for_task, 'tag', None),
                            'register_address': getattr(reg_for_task, 'address', None),
                            'poll_rate': getattr(reg_for_task, 'poll_rate', None),
                            'timestamp': timestamp,
                            'raw_value': str(read_result.get('raw_value')),
                            'value_float': read_result.get('value_float'),
                            'value_int': read_result.get('value_int', None),
                            'unit': unit,
                            'quality': read_result.get('quality'),
                            'is_alarm': False,
                        },
                    }
                    results_batch.append(rec)
                except Exception as e:
                    logger.exception("Erro ao montar record de leitura: %s", e)
                    continue

            if results_batch:
                await loop.run_in_executor(self._executor, self._process_batch_sync, results_batch)
                self._touch_last_seen()

            if sleep:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Polling loop for %s was cancelled.", self._key())
            raise
        except Exception as e:
            logger.exception("Unexpected error in poll loop for %s: %s", self._key(), e)
            await self._disconnect_adapter()
            self._mark_offline()
            if sleep:
                await asyncio.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, 30.0)

    async def start(self):
        if not self._polling_allowed:
            logger.info(
                "Polling desativado pelas configurações; ignorando PLC %s",
                self._key(),
            )
            return
        self._stop = False
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Erro ao aguardar encerramento do poller %s", self._key())
            self._task = None
        await self._disconnect_adapter()
        self._mark_offline()

    async def _run_loop(self):
        logger.info(f"PLCPoller starting for {self._key()}")

        while not self._stop:
            try:
                await self.poll_once(sleep=True)
            except asyncio.CancelledError:
                break

        await self._disconnect_adapter()
        self._mark_offline()
        logger.info(f"PLCPoller stopped for {self._key()}")



# ---------- Simple manager that keeps pollers by key (ip|vlan) ----------
class SimpleManager:
    def __init__(self, flask_app, *, settings: Optional[AppSettings] = None):
        self._pollers: Dict[str, ActivePLCPoller] = {}
        self._lock = asyncio.Lock()
        self.flask_app = flask_app
        self._settings = settings or get_app_settings(flask_app)

    @staticmethod
    def make_key(ip: str, vlan: Optional[int]) -> str:
        return f"{ip}|{vlan or 0}"

    async def add_plc(self, plc_orm: PLC, registers_provider):
        key = self.make_key(plc_orm.ip_address, plc_orm.vlan_id)
        async with self._lock:
            if key in self._pollers:
                logger.info(f"PLC already managed: {key}")
                return self._pollers[key]
            try:
                poller = ActivePLCPoller(
                    plc_orm,
                    registers_provider,
                    flask_app=self.flask_app,
                    settings=self._settings,
                )
            except TypeError:
                poller = ActivePLCPoller(
                    plc_orm,
                    registers_provider,
                    flask_app=self.flask_app,
                )
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
