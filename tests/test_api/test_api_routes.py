from datetime import datetime, timedelta, timezone

from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Data import DataLog
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Users import User, UserRole


def authenticate(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_get_data_optimized_returns_expected_payload(client, db):
    user = User(username="admin", email="admin@example.com", role=UserRole.ADMIN)
    user.set_password("secret")
    db.session.add(user)

    plc = PLC(name="PLC-API", ip_address="10.0.0.8", protocol="modbus", port=502, is_active=True)
    db.session.add(plc)
    db.session.flush()

    active_register = Register(
        plc_id=plc.id,
        name="Temp",
        address="10",
        register_type="holding",
        data_type="float",
        is_active=True,
    )
    inactive_register = Register(
        plc_id=plc.id,
        name="Pressure",
        address="11",
        register_type="holding",
        data_type="float",
        is_active=False,
    )
    db.session.add_all([active_register, inactive_register])
    db.session.flush()

    base_time = datetime.now(timezone.utc)
    for offset in range(3):
        db.session.add(
            DataLog(
                plc_id=plc.id,
                register_id=active_register.id,
                timestamp=base_time - timedelta(minutes=offset),
                value_float=20.0 + offset,
                quality="GOOD",
            )
        )

    db.session.add_all(
        [
            AlarmDefinition(
                plc_id=plc.id,
                register_id=active_register.id,
                name="High",
                condition_type="above",
                threshold_high=30.0,
                is_active=True,
            ),
            AlarmDefinition(
                plc_id=plc.id,
                register_id=active_register.id,
                name="Inactive",
                condition_type="above",
                threshold_high=40.0,
                is_active=False,
            ),
        ]
    )

    db.session.add_all(
        [
            Alarm(
                plc_id=plc.id,
                register_id=active_register.id,
                state="ACTIVE",
                priority="HIGH",
                message="Alarm active",
            ),
            Alarm(
                plc_id=plc.id,
                register_id=active_register.id,
                state="CLEARED",
                priority="LOW",
                message="Alarm cleared",
            ),
        ]
    )

    db.session.commit()

    authenticate(client, "admin", "secret")

    response = client.get("/api/get/data/clp/10.0.0.8")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["clp_id"] == plc.id
    assert payload["registers"] == {str(active_register.id): active_register.name}
    assert len(payload["data"]) == 3
    assert all(entry["register_id"] == active_register.id for entry in payload["data"])
    assert len(payload["alarms"]) == 1
    assert payload["alarms"][0]["state"] == "ACTIVE"
    assert len(payload["definitions_alarms"]) == 1


def test_get_data_optimized_returns_404_for_unknown_plc(client, db):
    user = User(username="user2", email="user2@example.com", role=UserRole.USER)
    user.set_password("password")
    db.session.add(user)
    db.session.commit()

    authenticate(client, "user2", "password")

    response = client.get("/api/get/data/clp/192.168.1.1")
    assert response.status_code == 404
    assert response.get_json()["error"] == "CLP not found"
