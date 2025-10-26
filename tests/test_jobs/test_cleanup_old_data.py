from datetime import datetime, timedelta, timezone

from src.jobs.cleanup_old_data import cleanup_old_datalogs
from src.models.Data import DataLog
from src.models.PLCs import PLC
from src.models.Registers import Register


def test_cleanup_job_removes_extra_entries(monkeypatch, app, db, plc_repo, register_repo):
    monkeypatch.setitem(cleanup_old_datalogs.__globals__, "create_app", lambda: app)

    plc = PLC(name="PLC-Cleanup", ip_address="10.0.0.7", protocol="modbus", port=502)
    plc_repo.add(plc)

    register = Register(
        plc_id=plc.id,
        name="Flow",
        address="5",
        register_type="holding",
        data_type="float",
    )
    register_repo.add(register)

    base_time = datetime.now(timezone.utc)
    for offset in range(5):
        db.session.add(
            DataLog(
                plc_id=plc.id,
                register_id=register.id,
                timestamp=base_time - timedelta(minutes=offset),
                value_float=offset,
            )
        )
    db.session.commit()

    deleted = cleanup_old_datalogs(keep_per_register=2, batch_delete_size=1)

    remaining = db.session.query(DataLog).filter_by(plc_id=plc.id, register_id=register.id).count()
    assert deleted == 3
    assert remaining == 2
