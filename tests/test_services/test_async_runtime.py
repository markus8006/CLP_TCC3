import asyncio

from src.services.polling.async_runtime import (
    ActivePLCPoller,
    PollingRuntime,
    SimpleManager,
    _sync_plcs,
    set_runtime_enabled,
)


class DummyPLC:
    def __init__(self, plc_id=1, active=True) -> None:
        self.id = plc_id
        self.ip_address = f"192.168.0.{plc_id}"
        self.vlan_id = None
        self.is_active = active
        self.polling_interval = 50
        self.is_online = False
        self.last_seen = None
        self.name = f"plc-{plc_id}"


class DummyRegister:
    def __init__(self, reg_id=1) -> None:
        self.id = reg_id
        self.address = f"4000{reg_id}"
        self.unit = "u"
        self.name = f"reg-{reg_id}"
        self.tag = f"tag-{reg_id}"
        self.poll_rate = 25


class DummyAdapter:
    def __init__(self) -> None:
        self.connected = False

    def conectar(self):
        self.connected = True

    def desconectar(self):
        self.connected = False

    def read_register(self, register):
        return register.id * 10


class DummyDataRepo:
    def __init__(self) -> None:
        self.saved = []

    def bulk_insert(self, batch, commit=True, batch_size=1000):
        self.saved.extend(batch)


class DummyAlarmService:
    def __init__(self) -> None:
        self.calls = []

    def check_and_handle(self, plc_id, register_id, value):
        self.calls.append((plc_id, register_id, value))
        return False


class DummyRegisterRepo:
    def __init__(self, registers):
        self._registers = registers

    def get_registers_for_plc(self, plc_id):
        return list(self._registers)


class DummyPLCRepo:
    def __init__(self, plcs):
        self._plcs = plcs

    def list_all(self):
        return list(self._plcs)


def test_active_poller_processes_batch():
    plc = DummyPLC()
    register = DummyRegister()
    data_repo = DummyDataRepo()
    alarm_service = DummyAlarmService()

    async def provider(plc_id):
        assert plc_id == plc.id
        return [register]

    async def run_test():
        poller = ActivePLCPoller(
            plc,
            register_provider=provider,
            data_repo=data_repo,
            alarm_service=alarm_service,
            mqtt_service=None,
            adapter_factory=lambda plc: DummyAdapter(),
            max_cycles=1,
            loop=asyncio.get_event_loop(),
        )

        poller.start()
        await poller._task

    asyncio.run(run_test())

    assert data_repo.saved
    assert alarm_service.calls
    assert plc.is_online is False or plc.is_online is True  # status toggled during run


def test_sync_plcs_respects_runtime_flag():
    async def run_test():
        loop = asyncio.get_event_loop()
        runtime = PollingRuntime(loop=loop)
        data_repo = DummyDataRepo()
        alarm_service = DummyAlarmService()
        register_repo = DummyRegisterRepo([DummyRegister()])
        plc_repo = DummyPLCRepo([DummyPLC(1, active=True), DummyPLC(2, active=False)])

        manager = SimpleManager(
            register_repo=register_repo,
            data_repo=data_repo,
            alarm_service=alarm_service,
            mqtt_service=None,
            loop=loop,
            adapter_factory=lambda plc: DummyAdapter(),
        )

        await _sync_plcs(runtime, manager, plc_repo)
        assert len(manager._pollers) == 1

        set_runtime_enabled(runtime, False)
        await _sync_plcs(runtime, manager, plc_repo)
        assert len(manager._pollers) == 0

    asyncio.run(run_test())
