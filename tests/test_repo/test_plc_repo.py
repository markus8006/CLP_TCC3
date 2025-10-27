# tests/test_plc_repo.py
import pytest
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.repository.Data_repository import DataLogRepo
from datetime import datetime, timezone

def test_plc_add_get_delete(plc_repo):
    # criar PLC
    plc = PLC(name="PLC-Test", ip_address="10.0.0.10", protocol="modbus", port=502, vlan_id=1)
    saved = plc_repo.add(plc)
    assert saved.id is not None

    # buscar por ip
    found = plc_repo.get_by_ip("10.0.0.10", vlan_id=1)
    assert found is not None
    assert found.ip_address == "10.0.0.10"

    # deletar por ip
    deleted = plc_repo.delete_by_ip("10.0.0.10", vlan_id=1)
    assert deleted is True

    # verificar que não existe mais
    notfound = plc_repo.get_by_ip("10.0.0.10", vlan_id=1)
    assert notfound is None

def test_register_and_datalog(register_repo, plc_repo, datalog_repo, monkeypatch):
    # evitar SQL específico não suportado no SQLite dos testes
    monkeypatch.setattr(DataLogRepo, "_cleanup_old_records_optimized", lambda self, records: None)
    # criar plc
    plc = PLC(name="PLC-Test2", ip_address="10.0.0.11", protocol="modbus", port=502, vlan_id=1)
    plc_repo.add(plc)

    # criar register
    reg = Register(plc_id=plc.id, name="Temp", address="0", register_type="holding", data_type="int16")
    register_repo.add(reg)

    # bulk insert datalog
    records = []
    ts = datetime.now(timezone.utc)
    for i in range(5):
        records.append({
            "plc_id": plc.id,
            "register_id": reg.id,
            "timestamp": ts,
            "raw_value": str(20 + i),
            "value_float": float(20 + i)
        })

    inserted = datalog_repo.bulk_insert(records, commit=True, batch_size=2)
    assert inserted == 5

    recent = datalog_repo.list_recent(plc.id, reg.id, limit=10)
    assert len(recent) == 5


def test_set_active_state_tracks_metadata(plc_repo):
    plc = PLC(name="PLC-LifeCycle", ip_address="10.0.0.12", protocol="modbus", port=502)
    plc_repo.add(plc)

    plc_repo.set_active_state(plc, False, actor="tester", reason="maintenance", source="manual")

    assert plc.is_active is False
    assert plc.deactivation_reason == "maintenance"
    assert plc.last_state_change_by == "tester"
    assert plc.activation_source == "manual"
    assert plc.deactivated_at is not None
    assert plc.status_changed_at is not None

    last_change = plc.status_changed_at

    plc_repo.set_active_state(plc, True, actor="tester", source="manual")

    assert plc.is_active is True
    assert plc.deactivation_reason is None
    assert plc.activated_at is not None
    assert plc.status_changed_at >= last_change
