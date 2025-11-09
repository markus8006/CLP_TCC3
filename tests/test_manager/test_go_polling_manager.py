import asyncio
from types import SimpleNamespace

import pytest

from src.manager.go_polling_manager import GoPollingManager, is_go_available


def test_go_polling_manager_triggers_polls(app, tmp_path):
    if not is_go_available():
        pytest.skip("Go toolchain not available")

    async def _run():
        poll_event = asyncio.Event()
        stop_event = asyncio.Event()

        class StubPoller:
            def __init__(self, plc, registers_provider, flask_app):
                self.registers_provider = registers_provider
                self.plc = plc
                self.calls = 0

            async def poll_once(self, sleep: bool = False):
                self.calls += 1
                poll_event.set()

            async def stop(self):
                stop_event.set()

        binary_path = tmp_path / "go_poller_bin"
        manager = GoPollingManager(app, binary_path=binary_path, poller_factory=StubPoller)

        plc = SimpleNamespace(id=1, ip_address="10.0.0.5", vlan_id=None, polling_interval=50)

        def registers_provider():
            return []

        poller = await manager.add_plc(plc, registers_provider)
        await asyncio.wait_for(poll_event.wait(), timeout=5)

        assert poller.calls >= 1

        await manager.remove_plc(plc.ip_address, plc.vlan_id)
        assert stop_event.is_set()

        await manager.shutdown()

    asyncio.run(_run())
