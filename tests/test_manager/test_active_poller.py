import asyncio
from types import SimpleNamespace

import pytest
from flask import Flask

from src.app.settings import AppSettings, store_settings
from src.manager.client_polling_manager import ActivePLCPoller
from src.services.polling_runtime import PollingRuntime, register_runtime


class DummyAdapter:
    def __init__(self, simulation: bool = False):
        self._connected = False
        self._simulation = simulation
        self.connect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self._connected = True
        return True

    async def disconnect(self):
        self._connected = False

    async def read_register(self, register):
        return None

    def is_connected(self):
        return self._connected

    def in_simulation(self):
        return self._simulation


@pytest.fixture
def poller_env(monkeypatch):
    app = Flask(__name__)
    settings = AppSettings()
    demo_settings = settings.demo.model_copy(update={"enabled": True, "disable_polling": True})
    features_settings = settings.features.model_copy(update={"enable_polling": False})
    settings = settings.model_copy(update={"demo": demo_settings, "features": features_settings})
    store_settings(app, settings)

    dummy_plc = SimpleNamespace(
        id=1,
        ip_address="127.0.0.1",
        vlan_id=None,
        protocol="modbus",
        name="PLC Sim",
        tags_as_list=lambda: ["sim"],
    )

    monkeypatch.setattr(
        "src.manager.client_polling_manager.get_adapter",
        lambda protocol, plc, settings=None: DummyAdapter(simulation=protocol.endswith("-sim")),
    )

    class FakeRepo:
        def get(self, _):
            return None

        def update(self, _):
            return None

    monkeypatch.setattr("src.manager.client_polling_manager.Plcrepo", FakeRepo())

    return app, settings, dummy_plc


def test_simulated_polling_allowed(poller_env):
    app, settings, dummy_plc = poller_env
    dummy_plc.protocol = "modbus-sim"

    poller = ActivePLCPoller(dummy_plc, lambda: [], app, settings=settings)

    assert poller._polling_allowed is True

    async def run():
        await poller.start()
        assert poller._task is not None
        await poller.stop()

    asyncio.run(run())


def test_hardware_polling_blocked(monkeypatch, poller_env):
    app, settings, dummy_plc = poller_env

    def make_adapter(protocol, plc, settings=None):
        return DummyAdapter(simulation=False)

    monkeypatch.setattr("src.manager.client_polling_manager.get_adapter", make_adapter)

    poller = ActivePLCPoller(dummy_plc, lambda: [], app, settings=settings)
    assert poller._polling_allowed is False

    async def run():
        await poller.poll_once(sleep=False)

    asyncio.run(run())
    # connect should never be attempted when polling is blocked
    assert poller.adapter.connect_calls == 0


def test_register_runtime_keeps_demo_simulation_enabled():
    app = Flask(__name__)
    settings = AppSettings()
    demo_settings = settings.demo.model_copy(update={"enabled": True, "disable_polling": True})
    features_settings = settings.features.model_copy(update={"enable_polling": False})
    settings = settings.model_copy(update={"demo": demo_settings, "features": features_settings})
    store_settings(app, settings)

    runtime = PollingRuntime(manager=SimpleNamespace())
    register_runtime(app, runtime)

    assert runtime.is_enabled() is True
