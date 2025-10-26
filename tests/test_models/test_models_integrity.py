from datetime import datetime, timezone

from src.app.extensions import db
from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Data import DataLog
from src.models.PLCs import Organization, PLC
from src.models.Registers import Register


def test_model_relationships_persist_correctly(db):
    root_org = Organization(name="Root")
    child_org = Organization(name="Child", parent=root_org)
    db.session.add_all([root_org, child_org])

    plc = PLC(
        name="PLC-1",
        description="Main controller",
        ip_address="192.168.0.10",
        protocol="modbus",
        port=502,
        organization=root_org,
    )
    db.session.add(plc)
    db.session.flush()

    register = Register(
        plc_id=plc.id,
        name="Temperature",
        address="40001",
        register_type="holding",
        data_type="float",
        is_active=True,
    )
    db.session.add(register)
    db.session.flush()

    datalog = DataLog(
        plc_id=plc.id,
        register_id=register.id,
        timestamp=datetime.now(timezone.utc),
        value_float=23.5,
        quality="GOOD",
    )
    db.session.add(datalog)

    alarm_definition = AlarmDefinition(
        plc_id=plc.id,
        register_id=register.id,
        name="High temperature",
        condition_type="above",
        threshold_high=25.0,
    )
    db.session.add(alarm_definition)
    db.session.flush()

    alarm = Alarm(
        plc_id=plc.id,
        register_id=register.id,
        alarm_definition_id=alarm_definition.id,
        state="ACTIVE",
        priority="HIGH",
        message="Temperature above limit",
        trigger_value=26.0,
        current_value=26.0,
    )
    db.session.add(alarm)
    db.session.commit()

    assert child_org.parent is root_org
    assert plc.organization is root_org
    assert register.plc is plc
    assert datalog in register.datalogs
    assert alarm_definition.register is register
    assert alarm.register is register
    assert alarm.plc is plc
