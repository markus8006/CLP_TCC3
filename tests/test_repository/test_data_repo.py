from datetime import datetime, timezone

from src.repository.Data_repository import DataLogRepo
from src.models.PLCs import PLC
from src.models.Registers import Register


def test_bulk_insert_triggers_cleanup(monkeypatch, datalog_repo, plc_repo, register_repo):
    plc = PLC(name="PLC-Bulk", ip_address="10.0.0.4", protocol="modbus", port=502)
    plc_repo.add(plc)

    register = Register(
        plc_id=plc.id,
        name="Pressure",
        address="3",
        register_type="holding",
        data_type="float",
    )
    register_repo.add(register)

    records = [
        {
            "plc_id": plc.id,
            "register_id": register.id,
            "timestamp": datetime.now(timezone.utc),
            "value_float": float(value),
        }
        for value in range(3)
    ]

    calls = []

    def fake_cleanup(self, cleanup_records):
        calls.append(cleanup_records)

    monkeypatch.setattr(DataLogRepo, "_cleanup_old_records_optimized", fake_cleanup)

    inserted = datalog_repo.bulk_insert(records, commit=True, batch_size=2)

    assert inserted == len(records)
    assert calls and calls[0] == records

    recent = datalog_repo.list_recent(plc.id, register.id, limit=5)
    assert len(recent) == len(records)
