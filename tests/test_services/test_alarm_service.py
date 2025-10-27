from types import SimpleNamespace

import pytest

from src.models.Alarms import AlarmDefinition
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Users import User, UserRole
from src.services.Alarms_service import AlarmService


@pytest.fixture
def alarm_service(db):
    return AlarmService(session=db.session)


def _create_plc_and_register(db):
    plc = PLC(name="PLC Sim", ip_address="127.0.0.1", protocol="modbus-sim", port=502)
    register = Register(
        plc=plc,
        name="Temperatura",
        address="1",
        register_type="holding",
        data_type="float",
    )
    db.session.add_all([plc, register])
    db.session.commit()
    return plc, register


def _create_users(db):
    users = [
        User(username="user", email="user@example.com", role=UserRole.USER, password_hash="x"),
        User(username="alarm", email="alarm@example.com", role=UserRole.ALARM_DEFINITION, password_hash="x"),
        User(username="mod", email="mod@example.com", role=UserRole.MODERATOR, password_hash="x"),
        User(username="admin", email="admin@example.com", role=UserRole.ADMIN, password_hash="x"),
    ]
    for user in users:
        db.session.add(user)
    db.session.commit()
    return users


def test_alarm_service_sends_emails_on_trigger_and_clear(db, alarm_service, monkeypatch):
    plc, register = _create_plc_and_register(db)
    _create_users(db)

    definition = AlarmDefinition(
        plc_id=plc.id,
        register_id=register.id,
        name="Alarme Temperatura",
        condition_type="above",
        setpoint=30.0,
        deadband=2.0,
        priority="HIGH",
        email_enabled=True,
        email_min_role=UserRole.MODERATOR,
    )
    db.session.add(definition)
    db.session.commit()

    captured = []

    def fake_send_email(subject, body, recipients):
        captured.append(SimpleNamespace(subject=subject, body=body, recipients=tuple(sorted(recipients))))
        return True

    monkeypatch.setattr("src.services.Alarms_service.send_email", fake_send_email)

    triggered = alarm_service.check_and_handle(plc.id, register.id, 45.0)
    assert triggered is True
    assert captured, "expected email on trigger"
    assert captured[-1].recipients == ("admin@example.com", "mod@example.com")
    assert "Alarme Temperatura" in captured[-1].subject

    cleared = alarm_service.check_and_handle(plc.id, register.id, 20.0)
    assert cleared is False
    assert len(captured) == 2
    assert "normalizado" in captured[-1].subject.lower()
