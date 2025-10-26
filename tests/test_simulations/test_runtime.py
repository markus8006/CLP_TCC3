from types import SimpleNamespace

from src.simulations.runtime import simulation_registry


def test_simulation_registry_generates_progressive_values():
    simulation_registry.clear()
    register = SimpleNamespace(id=1, data_type="int16")
    first = simulation_registry.next_value("modbus", register)
    second = simulation_registry.next_value("modbus", register)

    assert first["raw_value"] != second["raw_value"]
    assert isinstance(second["value_int"], int)


def test_simulation_registry_toggles_boolean():
    simulation_registry.clear()
    register = SimpleNamespace(id=2, data_type="bool")
    values = [simulation_registry.next_value("opcua", register)["raw_value"] for _ in range(3)]
    assert values[0] != values[1]
    assert values[1] != values[2]
