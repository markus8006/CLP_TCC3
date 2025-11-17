
"""Runtime assíncrono de polling inspirado na arquitetura descrita.

Componentes principais
----------------------
- :class:`ActivePLCPoller` executa o ciclo de polling de um único CLP
  mantendo o estado online/offline e aplicando *backoff* em falhas.
- :class:`SimpleManager` orquestra os pollers por chave ``ip|vlan``
  criando e encerrando conforme a configuração do banco.
- :class:`PollingRuntime` guarda o *event loop*, cache de PLCs e um
  gatilho de sincronização (:class:`asyncio.Event`).
- :func:`client_polling_service` implementa o laço principal que compara
  o cache com o banco e garante que apenas CLPs activos possuam pollers
  em execução.
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from src.repository.Data_repository import DataLogRepo
from src.repository.PLC_repository import PLCRepo, Plcrepo
from src.repository.Registers_repository import RegRepo, RegisterRepo
from src.services.Alarms_service import AlarmService
from src.services.drivers.factory import get_driver
from src.services.mqtt_service import MqttPublisherService
from src.utils.logs import logger

RegisterProvider = Callable[[int], Awaitable[Iterable[Any]]]


@dataclass
class PollingRuntime:
    """Guarda estado global do serviço de polling."""

    cache: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    trigger: asyncio.Event = field(default_factory=asyncio.Event)
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_event_loop)

    def notify(self) -> None:
        """Sinaliza que a configuração foi alterada e precisa ressincronizar."""
        if not self.trigger.is_set():
            self.trigger.set()


class ActivePLCPoller:
    """Executa o polling de um único CLP com *backoff* e publicação MQTT."""

    def __init__(
        self,
        plc: Any,
        *,
        register_provider: RegisterProvider,
        data_repo: DataLogRepo,
        alarm_service: AlarmService,
        mqtt_service: Optional[MqttPublisherService] = None,
        adapter_factory: Callable[[Any], Any] = get_driver,
        max_concurrency: int = 10,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        max_cycles: Optional[int] = None,
    ) -> None:
        self.plc = plc
        self.register_provider = register_provider
        self.data_repo = data_repo
        self.alarm_service = alarm_service
        self.mqtt_service = mqtt_service
        self.adapter_factory = adapter_factory
        self.loop = loop or asyncio.get_event_loop()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_cycles = max_cycles

    @property
    def key(self) -> str:
        vlan = getattr(self.plc, "vlan_id", None) or 0
        return f"{getattr(self.plc, 'ip_address', '')}|{vlan}"

    @property
    def interval_seconds(self) -> float:
        interval_ms = max(getattr(self.plc, "polling_interval", 1000) or 1000, 250)
        return interval_ms / 1000.0

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = self.loop.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        backoff = 1.0
        cycles = 0
        while not self._stop_event.is_set():
            adapter = self.adapter_factory(self.plc)
            if adapter is None:
                logger.error("[POLLING] Nenhum adaptador para PLC %s", getattr(self.plc, "id", "?"))
                return

            try:
                await self._maybe_async(adapter, "conectar")
                self._mark_online()
                await self._poll_once(adapter)
                backoff = 1.0
                cycles += 1
                if self._max_cycles and cycles >= self._max_cycles:
                    break
                await asyncio.wait_for(self._stop_event.wait(self.interval_seconds), timeout=None)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[POLLING] Falha no poller do PLC %s — aplicando backoff",
                    getattr(self.plc, "id", "?"),
                )
                self._mark_offline()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            finally:
                try:
                    await self._maybe_async(adapter, "desconectar")
                except Exception:
                    logger.exception("[POLLING] Erro ao desconectar PLC %s", getattr(self.plc, "id", "?"))

        self._mark_offline()

    async def _poll_once(self, adapter: Any) -> None:
        registers = await self.register_provider(getattr(self.plc, "id", 0))
        registers = list(registers or [])
        if not registers:
            logger.warning("[POLLING] CLP %s sem registradores activos", getattr(self.plc, "id", "?"))
            return

        tasks = [self.loop.create_task(self._read_single(adapter, reg)) for reg in registers]
        results: List[Dict[str, Any]] = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                results.append(result)

        if results:
            await self.loop.run_in_executor(None, self._process_batch_sync, results)

    async def _read_single(self, adapter: Any, register: Any) -> Optional[Dict[str, Any]]:
        async with self._semaphore:
            try:
                value = await self._invoke_read(adapter, register)
                timestamp = datetime.now(timezone.utc)
                measurement = self._build_measurement(register, value, timestamp)
                return measurement
            except Exception:
                logger.exception(
                    "[POLLING] Falha ao ler registrador %s do PLC %s",
                    getattr(register, "id", "?"),
                    getattr(self.plc, "id", "?"),
                )
                return None

    async def _invoke_read(self, adapter: Any, register: Any) -> Any:
        fn = getattr(adapter, "read_register", None)
        args: Any = register
        if fn is None:
            fn = getattr(adapter, "ler", None)
            args = [register]
        if fn is None:
            raise RuntimeError("Adaptador não suporta leitura")

        if inspect.iscoroutinefunction(fn):
            return await fn(args)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, args)

    def _build_measurement(self, register: Any, value: Any, timestamp: datetime) -> Dict[str, Any]:
        try:
            value_float = float(value) if value is not None else None
        except (TypeError, ValueError):
            value_float = None

        return {
            "plc_id": getattr(self.plc, "id", None),
            "register_id": getattr(register, "id", None),
            "timestamp": timestamp,
            "raw_value": None if value is None else str(value),
            "value_float": value_float,
            "value_int": value if isinstance(value, int) else None,
            "quality": "ok",
            "unit": getattr(register, "unit", None),
            "plc_name": getattr(self.plc, "name", None),
            "register_name": getattr(register, "name", None),
            "register_tag": getattr(register, "tag", None),
            "address": getattr(register, "address", None),
            "poll_rate": getattr(register, "poll_rate", getattr(self.plc, "polling_interval", None)),
        }

    def _process_batch_sync(self, batch: List[Dict[str, Any]]) -> None:
        for item in batch:
            try:
                is_alarm = self.alarm_service.check_and_handle(
                    item.get("plc_id"), item.get("register_id"), item.get("value_float")
                )
            except Exception:
                logger.exception(
                    "[POLLING] Erro ao avaliar alarmes para plc=%s reg=%s",
                    item.get("plc_id"),
                    item.get("register_id"),
                )
                is_alarm = False
            item["is_alarm"] = is_alarm

        try:
            self.data_repo.bulk_insert(batch, commit=True, batch_size=1000)
        except Exception:
            logger.exception("[POLLING] Falha ao persistir lote de leituras")

        if self.mqtt_service:
            try:
                self.mqtt_service.publish_measurements(batch)
            except Exception:
                logger.exception("[POLLING] Falha ao publicar lote MQTT")

    async def _maybe_async(self, adapter: Any, method: str) -> None:
        fn = getattr(adapter, method, None)
        if fn is None:
            return
        if inspect.iscoroutinefunction(fn):
            await fn()
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, fn)

    def _mark_online(self) -> None:
        try:
            if hasattr(self.plc, "is_online"):
                self.plc.is_online = True
            if hasattr(self.plc, "last_seen"):
                self.plc.last_seen = datetime.now(timezone.utc)
            if self.mqtt_service:
                self.mqtt_service.publish_connectivity_event(self.plc, "online")
        except Exception:
            logger.exception("[POLLING] Falha ao marcar PLC %s online", getattr(self.plc, "id", "?"))

    def _mark_offline(self) -> None:
        try:
            if hasattr(self.plc, "is_online"):
                self.plc.is_online = False
            if self.mqtt_service:
                self.mqtt_service.publish_connectivity_event(self.plc, "offline")
        except Exception:
            logger.exception("[POLLING] Falha ao marcar PLC %s offline", getattr(self.plc, "id", "?"))


class SimpleManager:
    """Armazena e controla o ciclo de vida dos pollers activos."""

    def __init__(
        self,
        *,
        register_repo: RegRepo,
        data_repo: DataLogRepo,
        alarm_service: AlarmService,
        mqtt_service: Optional[MqttPublisherService] = None,
        adapter_factory: Callable[[Any], Any] = get_driver,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.register_repo = register_repo
        self.data_repo = data_repo
        self.alarm_service = alarm_service
        self.mqtt_service = mqtt_service
        self.adapter_factory = adapter_factory
        self.loop = loop or asyncio.get_event_loop()
        self._pollers: Dict[str, ActivePLCPoller] = {}

    def add_plc(self, plc: Any) -> None:
        key = self._build_key(plc)
        if key in self._pollers:
            return

        async def provider(plc_id: int) -> Iterable[Any]:
            return self.register_repo.get_registers_for_plc(plc_id)

        poller = ActivePLCPoller(
            plc,
            register_provider=provider,
            data_repo=self.data_repo,
            alarm_service=self.alarm_service,
            mqtt_service=self.mqtt_service,
            adapter_factory=self.adapter_factory,
            loop=self.loop,
        )
        self._pollers[key] = poller
        poller.start()

    async def remove_plc(self, plc: Any) -> None:
        key = self._build_key(plc)
        poller = self._pollers.pop(key, None)
        if poller:
            await poller.stop()

    async def shutdown(self) -> None:
        for poller in list(self._pollers.values()):
            await poller.stop()
        self._pollers.clear()

    def _build_key(self, plc: Any) -> str:
        vlan = getattr(plc, "vlan_id", None) or 0
        return f"{getattr(plc, 'ip_address', '')}|{vlan}"


async def client_polling_service(
    runtime: PollingRuntime,
    *,
    plc_repo: PLCRepo = Plcrepo,
    register_repo: Optional[RegisterRepo] = None,
    data_repo: Optional[DataLogRepo] = None,
    alarm_service: Optional[AlarmService] = None,
    mqtt_service: Optional[MqttPublisherService] = None,
    interval: float = 10.0,
) -> None:
    """Loop assíncrono que sincroniza pollers com o banco."""

    alarm_service = alarm_service or AlarmService()
    register_repo = register_repo or RegRepo
    data_repo = data_repo or DataLogRepo()
    manager = SimpleManager(
        register_repo=register_repo,
        data_repo=data_repo,
        alarm_service=alarm_service,
        mqtt_service=mqtt_service,
        loop=runtime.loop,
    )

    try:
        while True:
            await _sync_plcs(runtime, manager, plc_repo)
            runtime.trigger.clear()
            try:
                await asyncio.wait_for(runtime.trigger.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    finally:
        await manager.shutdown()


def set_runtime_enabled(runtime: PollingRuntime, enabled: bool) -> None:
    """Altera a flag global e desperta o loop principal."""
    runtime.enabled = enabled
    runtime.notify()


async def _sync_plcs(runtime: PollingRuntime, manager: SimpleManager, plc_repo: PLCRepo) -> None:
    plcs = plc_repo.list_all() or []
    active_plcs = [plc for plc in plcs if getattr(plc, "is_active", True)]

    if not runtime.enabled:
        await manager.shutdown()
        runtime.cache.clear()
        return

    for plc in active_plcs:
        key = manager._build_key(plc)
        cached = runtime.cache.get(key)
        if cached and cached.get("id") == getattr(plc, "id", None):
            continue
        runtime.cache[key] = {"id": getattr(plc, "id", None), "active": True}
        manager.add_plc(plc)

    cached_keys = set(runtime.cache.keys())
    active_keys = {manager._build_key(plc) for plc in active_plcs}
    for stale_key in cached_keys - active_keys:
        dummy_plc = type("_", (), {})()
        setattr(dummy_plc, "ip_address", stale_key.split("|")[0])
        vlan_part = stale_key.split("|")[1]
        setattr(dummy_plc, "vlan_id", int(vlan_part) if vlan_part else None)
        await manager.remove_plc(dummy_plc)
        runtime.cache.pop(stale_key, None)
