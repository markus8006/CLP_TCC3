import asyncio

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.services.client_polling_service import start_polling_service


class DummyPollingManager:
    def __init__(self):
        self.calls = []

    async def add_plc(self, plc, register_provider):
        self.calls.append((plc, register_provider()))


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

    asyncio.run(start_polling_service(app, manager))

    assert len(manager.calls) == 1
    (plc, registers), = manager.calls
    assert plc.id == active_plc.id
    assert registers[0].id == register.id
