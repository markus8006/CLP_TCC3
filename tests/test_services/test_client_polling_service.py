import asyncio

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.services.client_polling_service import start_polling_service, sync_polling_state


class DummyPollingManager:
    def __init__(self):
        self.add_calls = []
        self.remove_calls = []

    @staticmethod
    def make_key(ip: str, vlan_id):
        return f"{ip}|{vlan_id or 0}"

    async def add_plc(self, plc, register_provider):
        self.add_calls.append((plc, register_provider()))

    async def remove_plc(self, ip, vlan_id=None):
        self.remove_calls.append((ip, vlan_id))


def test_start_polling_service_only_adds_active_plcs(app, db, plc_repo, register_repo):
    active_plc = PLC(name="PLC-Active", ip_address="10.0.0.5", protocol="modbus", port=502, is_active=True)
    inactive_plc = PLC(name="PLC-Inactive", ip_address="10.0.0.6", protocol="modbus", port=502, is_active=False)
    plc_repo.add(active_plc)
    plc_repo.add(inactive_plc)

    register = Register(
        plc_id=active_plc.id,
        name="Level",
        address="4",
        register_type="holding",
        data_type="float",
        is_active=True,
    )
    register_repo.add(register)

    manager = DummyPollingManager()

    cache = asyncio.run(start_polling_service(app, manager))

    assert len(manager.add_calls) == 1
    (plc, registers), = manager.add_calls
    assert plc.id == active_plc.id
    assert registers[0].id == register.id

    key = manager.make_key(active_plc.ip_address, active_plc.vlan_id)
    assert key in cache
    assert cache[key][0] is True


def test_sync_polling_state_tracks_activation_changes(app, db, plc_repo, register_repo):
    plc = PLC(
        name="PLC-Dynamic",
        ip_address="10.0.0.7",
        protocol="modbus",
        port=502,
        is_active=True,
    )
    plc_repo.add(plc)

    register = Register(
        plc_id=plc.id,
        name="Pressure",
        address="5",
        register_type="holding",
        data_type="float",
        is_active=True,
    )
    register_repo.add(register)

    manager = DummyPollingManager()
    cache = asyncio.run(start_polling_service(app, manager))
    assert len(manager.add_calls) == 1

    manager.add_calls.clear()
    manager.remove_calls.clear()

    plc_repo.set_active_state(plc, False, reason="maintenance")
    cache = asyncio.run(sync_polling_state(app, manager, cache))

    assert manager.remove_calls == [(plc.ip_address, plc.vlan_id)]
    key = manager.make_key(plc.ip_address, plc.vlan_id)
    assert cache[key][0] is False

    manager.add_calls.clear()
    manager.remove_calls.clear()

    plc_repo.set_active_state(plc, True)
    cache = asyncio.run(sync_polling_state(app, manager, cache))

    assert len(manager.add_calls) == 1
    assert manager.remove_calls == []
    assert cache[key][0] is True
