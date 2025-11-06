import pytest

from src.services.address_mapping import AddressMappingEngine


@pytest.fixture()
def engine() -> AddressMappingEngine:
    return AddressMappingEngine()


def test_normalize_siemens_byte_and_bit(engine: AddressMappingEngine) -> None:
    normalized = engine.normalize("siemens", "DB1.DBX0.7")
    assert normalized == {"db": 1, "area": "DBX", "byte": 0, "bit": 7}


def test_normalize_siemens_invalid(engine: AddressMappingEngine) -> None:
    with pytest.raises(ValueError):
        engine.normalize("siemens", "INVALID")


def test_normalize_modbus_numeric(engine: AddressMappingEngine) -> None:
    normalized = engine.normalize("modbus", "40001")
    assert normalized == {"function": 4, "address": 1}


def test_normalize_modbus_prefixed(engine: AddressMappingEngine) -> None:
    normalized = engine.normalize("modbus", "400123")
    assert normalized == {"function": 4, "address": 123}


def test_normalize_passthrough_protocols(engine: AddressMappingEngine) -> None:
    assert engine.normalize("ethernetip", "Program:Main.Motor.Speed") == {
        "tag": "Program:Main.Motor.Speed"
    }
    assert engine.normalize("opcua", "ns=2;s=Motor1.Temperature") == {
        "node_id": "ns=2;s=Motor1.Temperature"
    }
    assert engine.normalize("profinet", "slot1.index5") == {"index": "slot1.index5"}
    assert engine.normalize("unknown", "SOME") == {"raw": "SOME"}
