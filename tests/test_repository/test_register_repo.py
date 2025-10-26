from src.models.PLCs import PLC
from src.models.Registers import Register


def test_register_repo_filters_active_registers(register_repo, plc_repo):
    plc = PLC(name="PLC-Active", ip_address="10.0.0.2", protocol="modbus", port=502)
    plc_repo.add(plc)

    active = Register(
        plc_id=plc.id,
        name="Active",
        address="1",
        register_type="holding",
        data_type="int",
        is_active=True,
    )
    inactive = Register(
        plc_id=plc.id,
        name="Inactive",
        address="2",
        register_type="holding",
        data_type="int",
        is_active=False,
    )
    register_repo.add(active)
    register_repo.add(inactive)

    result = register_repo.get_registers_for_plc(plc.id)
    assert [r.id for r in result] == [active.id]


def test_plc_repo_upsert_updates_existing(plc_repo, db):
    plc = PLC(name="PLC-Upsert", ip_address="10.0.0.3", protocol="modbus", port=502)
    plc_repo.add(plc)

    replacement = PLC(
        name="PLC-Updated",
        ip_address="10.0.0.3",
        protocol="modbus",
        port=502,
        vlan_id=plc.vlan_id,
        is_active=False,
    )

    updated = plc_repo.upsert_by_ip(replacement)
    db.session.refresh(updated)

    assert updated.name == "PLC-Updated"
    assert updated.is_active is False
