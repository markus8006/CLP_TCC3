import asyncio
import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.utils.logs import logger

if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem
    from src.services.polling_runtime import PollingRuntime


StateCache = Dict[str, Tuple[bool, Optional[datetime], bool]]


def _split_key(key: str) -> Tuple[str, Optional[int]]:
    ip, raw_vlan = key.split("|", 1)
    vlan_id = int(raw_vlan) if raw_vlan and raw_vlan != "0" else None
    return ip, vlan_id


def _ensure_runtime(runtime_or_manager: Any) -> Any:
    if hasattr(runtime_or_manager, "manager"):
        return runtime_or_manager

    placeholder = SimpleNamespace()
    placeholder.manager = runtime_or_manager
    placeholder.cache = {}
    placeholder.loop = None
    placeholder.trigger = None
    placeholder._enabled = True

    def _is_enabled() -> bool:
        return placeholder._enabled

    def _set_enabled(state: bool) -> None:
        placeholder._enabled = state

    def _ensure_trigger() -> asyncio.Event:
        if placeholder.trigger is None:
            placeholder.trigger = asyncio.Event()
        return placeholder.trigger

    placeholder.is_enabled = _is_enabled
    placeholder.set_enabled = _set_enabled
    placeholder.ensure_trigger = _ensure_trigger
    return placeholder


async def sync_polling_state(
    app,
    manager: Any,
    state_cache: Optional[StateCache] = None,
    *,
    bootstrap: bool = False,
    polling_enabled: bool = True,
) -> StateCache:
    """Sincroniza o estado dos pollers com base na flag ``is_active`` dos CLPs."""

    cache: StateCache = state_cache or {}
    with app.app_context():
        plcs = Plcrepo.list_all()
        db_keys = set()
        for plc in plcs:
            key = manager.make_key(plc.ip_address, plc.vlan_id)
            db_keys.add(key)
            previous_state = cache.get(key)
            status_token = (
                plc.is_active and polling_enabled,
                plc.status_changed_at or plc.updated_at,
                polling_enabled,
            )
            registers_provider = (
                lambda plc_id=plc.id: RegRepo.get_registers_for_plc(plc_id)
            )

            if plc.is_active and polling_enabled:
                needs_add = (
                    bootstrap
                    or previous_state is None
                    or not previous_state[0]
                    or previous_state[1] != status_token[1]
                )
                if needs_add:
                    await manager.add_plc(plc, registers_provider)
            else:
                if previous_state and previous_state[0]:
                    await manager.remove_plc(plc.ip_address, plc.vlan_id)
                if plc.is_online:
                    plc.is_online = False
                    plc.last_seen = None
                    Plcrepo.update(plc)

            cache[key] = status_token

        # Remove pollers para CLPs eliminados
        removed_keys = set(cache.keys()) - db_keys
        for key in list(removed_keys):
            active, _, _ = cache.pop(key)
            if active:
                ip, vlan = _split_key(key)
                await manager.remove_plc(ip, vlan)

    return cache


async def start_polling_service(app, runtime_or_manager: Any) -> StateCache:
    runtime = _ensure_runtime(runtime_or_manager)
    logger.process("Iniciando serviço de polling...")
    cache: StateCache = getattr(runtime, "cache", {}) or {}
    cache = await sync_polling_state(
        app,
        runtime.manager,
        cache,
        bootstrap=True,
        polling_enabled=runtime.is_enabled(),
    )
    logger.info("Estado inicial de polling sincronizado com %d CLPs.", len(cache))
    runtime.cache = cache
    return cache


async def main_async(app, runtime_or_manager: Any, interval: float = 10.0):
    runtime = _ensure_runtime(runtime_or_manager)
    runtime.cache = await start_polling_service(app, runtime)
    trigger = runtime.ensure_trigger()
    while True:
        try:
            await asyncio.wait_for(trigger.wait(), timeout=interval)
            trigger.clear()
        except asyncio.TimeoutError:
            pass
        runtime.cache = await sync_polling_state(
            app,
            runtime.manager,
            runtime.cache,
            polling_enabled=runtime.is_enabled(),
        )


def run_async_polling(app, runtime_or_manager: Any, interval: float = 10.0):
    runtime = _ensure_runtime(runtime_or_manager)
    loop = asyncio.new_event_loop()
    runtime.loop = loop
    asyncio.set_event_loop(loop)
    runtime.ensure_trigger()
    try:
        loop.run_until_complete(main_async(app, runtime, interval=interval))
    finally:  # pragma: no cover - encerramento do serviço
        loop.close()
