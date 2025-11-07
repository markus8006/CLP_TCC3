import pytest

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Users import User, UserRole
from src.services.tag_simulation_service import get_simulated_tags
from src.utils.tags import normalize_tag


PROTOCOL_EXPECTATIONS = [
    (
        "modbus",
        {"port": 502, "unit_id": 1},
        {"40001", "40002", "00010"},
        {
            normalize_tag("TEMP_PROCESSO"),
            normalize_tag("PRESSAO_LINHA"),
            normalize_tag("ESTADO_BOMBA"),
        },
    ),
    (
        "s7",
        {"port": 102, "rack_slot": "0,2"},
        {"DB1.DBW0", "DB1.DBW4", "DB1.DBX8.0"},
        {
            normalize_tag("DB1.Temperatura"),
            normalize_tag("DB1.Nivel"),
            normalize_tag("DB1.BombaAtiva"),
        },
    ),
    (
        "opcua",
        {"port": 4840},
        {
            "ns=2;s=Fabrica/Misturador/Temperatura",
            "ns=2;s=Fabrica/Misturador/Estado",
            "ns=2;s=Fabrica/Esteira/Velocidade",
        },
        {
            normalize_tag("Objects/Fábrica/Misturador/Temperatura"),
            normalize_tag("Objects/Fábrica/Misturador/Estado"),
            normalize_tag("Objects/Fábrica/Esteira/Velocidade"),
        },
    ),
    (
        "ethernetip",
        {"port": 44818},
        {"Mixer.Temperature", "Mixer.Level", "Conveyor.MotorRunning"},
        {
            normalize_tag("Mixer.Temperature"),
            normalize_tag("Mixer.Level"),
            normalize_tag("Conveyor.MotorRunning"),
        },
    ),
    (
        "beckhoff",
        {"port": 48898},
        {
            "MAIN.fbPress.Pressure",
            "MAIN.fbPress.IsRunning",
            "MAIN.fbPress.Setpoint",
        },
        {
            normalize_tag("MAIN.fbPress.Pressure"),
            normalize_tag("MAIN.fbPress.IsRunning"),
            normalize_tag("MAIN.fbPress.Setpoint"),
        },
    ),
    (
        "profinet",
        {"port": 10201},
        {"16/1", "32/2"},
        {
            normalize_tag("AI_Temperatura"),
            normalize_tag("DI_Emergencia"),
        },
    ),
    (
        "dnp3",
        {"port": 20000},
        {"g30v1/12", "g1v2/5"},
        {
            normalize_tag("AI_Subestacao_1"),
            normalize_tag("DI_Subestacao_1"),
        },
    ),
    (
        "iec104",
        {"port": 2404},
        {"101", "16"},
        {
            normalize_tag("TI.1.101"),
            normalize_tag("SP.1.16"),
        },
    ),
]


@pytest.mark.parametrize(
    "protocol, extra, expected_addresses, expected_tags",
    PROTOCOL_EXPECTATIONS,
    ids=[scenario[0] for scenario in PROTOCOL_EXPECTATIONS],
)
def test_discover_creates_registers_for_protocol(
    client, db, monkeypatch, protocol, extra, expected_addresses, expected_tags
):
    monkeypatch.setattr(
        "flask_login.mixins.UserMixin.is_active",
        property(lambda self: True),
        raising=False,
    )
    monkeypatch.setattr(
        "flask_login.mixins.UserMixin.is_authenticated",
        property(lambda self: True),
        raising=False,
    )

    user = User(username="admin", email="admin@example.com", role=UserRole.ADMIN)
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    user = db.session.merge(user)

    plc = PLC(
        name=f"PLC_{protocol.upper()}",
        ip_address=f"10.0.{len(expected_addresses)}.{len(expected_tags)}",
        protocol=protocol,
        port=extra.get("port", 0),
        is_active=True,
    )
    if "unit_id" in extra:
        plc.unit_id = extra["unit_id"]
    if "rack_slot" in extra:
        plc.rack_slot = extra["rack_slot"]

    db.session.add(plc)
    db.session.commit()

    async def fake_discover(protocol_name, params):
        assert protocol_name == protocol
        return get_simulated_tags(protocol_name)

    monkeypatch.setattr("src.app.routes.api.plc_api.discover_tags_async", fake_discover)

    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.post(f"/api/plcs/{plc.id}/discover")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["registers_created"] == len(expected_addresses)
    assert payload["registers_updated"] == 0
    assert payload["discovered"] == len(get_simulated_tags(protocol))
    assert len(payload["register_ids"]) == len(expected_addresses)

    registers = Register.query.filter_by(plc_id=plc.id).all()
    assert len(registers) == len(expected_addresses)
    assert {register.address for register in registers} == expected_addresses
    assert {register.tag for register in registers if register.tag} == expected_tags
    assert all(register.protocol == protocol for register in registers)

    db.session.refresh(plc)
    assert set(plc.tags_as_list()) == expected_tags
    assert set(payload["tags"]) == expected_tags
