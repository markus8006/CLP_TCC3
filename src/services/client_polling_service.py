import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.utils.logs import logger

StateCache = Dict[str, Tuple[bool, Optional[datetime]]]


def _split_key(key: str) -> Tuple[str, Optional[int]]:
    ip, raw_vlan = key.split("|", 1)
    vlan_id = int(raw_vlan) if raw_vlan and raw_vlan != "0" else None
    return ip, vlan_id


async def sync_polling_state(
    app,
    manager: Any,
    state_cache: Optional[StateCache] = None,
    *,
    bootstrap: bool = False,
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
            status_token = (plc.is_active, plc.status_changed_at or plc.updated_at)
            registers_provider = (
                lambda plc_id=plc.id: RegRepo.get_registers_for_plc(plc_id)
            )

            if plc.is_active:
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
            active, _ = cache.pop(key)
            if active:
                ip, vlan = _split_key(key)
                await manager.remove_plc(ip, vlan)

    return cache


async def start_polling_service(app, manager: Any) -> StateCache:
    logger.process("Iniciando serviço de polling...")
    cache: StateCache = {}
    cache = await sync_polling_state(app, manager, cache, bootstrap=True)
    logger.info("Estado inicial de polling sincronizado com %d CLPs.", len(cache))
    return cache


async def main_async(app, manager: Any, interval: float = 10.0):
    cache = await start_polling_service(app, manager)
    while True:
        await asyncio.sleep(interval)
        cache = await sync_polling_state(app, manager, cache)


def run_async_polling(app, manager: Any):
    asyncio.run(main_async(app, manager))
