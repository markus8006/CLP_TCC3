import os
from datetime import datetime, timezone, timedelta

from src.consumers.data_processor import PLCDataProcessor
from src.models.PLCs import PLC


def test_connectivity_updates_when_processing_batch(db, app):
    plc = PLC(
        name="OPC UA Remote",
        ip_address="126.0.0.3",
        protocol="opcua",
        port=4840,
        is_online=False,
    )
    db.session.add(plc)
    db.session.commit()

    previous_env = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = "testing"

    processor = PLCDataProcessor(batch_size=1, flush_interval=0.1, app=app)

    timestamp = datetime.now(timezone.utc) + timedelta(seconds=1)
    batch = [
        {
            "plc_id": plc.id,
            "register_id": 1,
            "timestamp": timestamp,
            "value_float": 42.0,
        }
    ]

    try:
        processor._update_connectivity(batch)
    finally:
        processor.shutdown()
        if previous_env is not None:
            os.environ["APP_ENV"] = previous_env
        else:
            os.environ.pop("APP_ENV", None)

    refreshed = db.session.get(PLC, plc.id)
    assert refreshed.is_online is True
    assert refreshed.last_seen.replace(tzinfo=timezone.utc) == timestamp
