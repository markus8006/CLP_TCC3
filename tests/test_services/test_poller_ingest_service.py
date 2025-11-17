from datetime import datetime, timedelta, timezone

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.services.poller_ingest_service import process_poller_payload


def test_offline_respects_register_poll_rate(db):
    session = db.session

    plc = PLC(
        name="Slow PLC",
        ip_address="10.0.0.50",
        protocol="modbus",
        port=502,
        polling_interval=1000,
        timeout=5000,
        is_online=True,
    )
    plc.last_seen = datetime.now(timezone.utc)
    session.add(plc)
    session.flush()

    register = Register(
        plc_id=plc.id,
        name="Slow register",
        address="40001",
        register_type="holding",
        data_type="int",
        poll_rate=15000,
    )
    session.add(register)
    session.commit()

    payload = {
        "plc_id": plc.id,
        "register_id": register.id,
        "status": "offline",
        # Only 10s after last_seen; should stay online because poll_rate is 15s
        "timestamp": plc.last_seen + timedelta(seconds=10),
        "value": 123,
    }

    process_poller_payload(payload, session=session)

    refreshed_plc = session.get(PLC, plc.id)
    refreshed_register = session.get(Register, register.id)

    assert refreshed_plc.is_online is True
    assert refreshed_register.error_count == 1
    assert refreshed_register.last_error == "offline"
