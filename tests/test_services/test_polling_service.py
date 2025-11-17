import time

from src.services.polling.polling_service import PollingService


class DummyPLC:
    def __init__(self) -> None:
        self.id = 1
        self.protocol = "modbus"
        self.polling_interval = 50
        self.ip_address = "127.0.0.1"
        self.port = 502


class DummyRegister:
    def __init__(self) -> None:
        self.id = 1
        self.address = "40001"
        self.unit = "u"


class DummyPLCRepo:
    def __init__(self, plcs) -> None:
        self._plcs = plcs

    def list_all(self):
        return self._plcs


class DummyRegisterRepo:
    def __init__(self, registers) -> None:
        self._registers = registers

    def get_registers_for_plc(self, plc_id):
        return self._registers


class DummyDataRepo:
    def __init__(self) -> None:
        self.saved = []

    def registrar_leitura(self, plc, register, valor):
        self.saved.append((plc.id, register.id, valor))


def test_polling_service_executes_worker(monkeypatch, app):
    monkeypatch.setattr(
        "src.services.polling.polling_service.get_polling_enabled", lambda default=True: True
    )
    plc = DummyPLC()
    register = DummyRegister()
    data_repo = DummyDataRepo()

    service = PollingService(
        app,
        plc_repo=DummyPLCRepo([plc]),
        register_repo=DummyRegisterRepo([register]),
        data_repo=data_repo,
    )

    service.start()
    time.sleep(0.2)
    service.stop()

    assert data_repo.saved
