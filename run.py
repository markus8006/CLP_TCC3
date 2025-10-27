import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.app import create_app
from src.manager.client_polling_manager import SimpleManager
from src.models import PLC, Register
from src.models.Alarms import AlarmDefinition
from src.repository.Alarms_repository import AlarmDefinitionRepo
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.services.client_polling_service import run_async_polling
from src.services.polling_runtime import PollingRuntime, register_runtime
from src.services.settings_service import get_polling_enabled
from src.simulations.runtime import simulation_registry
from src.utils.logs import logger

# ===========================================================
# CONFIGURAÇÕES
# ===========================================================
CLPS_POR_PROTOCOLO = 5
MAX_THREADS = 4  # reservado para futura paralelização


# ===========================================================
# MODELOS DE TEMPLATE
# ===========================================================
@dataclass(frozen=True)
class RegisterTemplate:
    name: str
    address: str
    register_type: str
    data_type: str
    unit: Optional[str] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    poll_rate: int = 1000
    length: int = 1
    alarm: Optional[Dict[str, object]] = None


@dataclass(frozen=True)
class ProtocolConfig:
    protocol: str
    prefix: str
    port: int
    first_octet: int
    description_template: str
    simulation_key: str
    register_templates: List[RegisterTemplate]
    ip_offset: int = 0
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    rack_slot: Optional[str] = None
    unit_id: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    polling_interval: int = 1000
    timeout: int = 5000


# ===========================================================
# CONFIGURAÇÃO DOS PROTOCOLOS
# ===========================================================
PROTOCOL_CONFIGS: Dict[str, ProtocolConfig] = {
    "s7": ProtocolConfig(
        protocol="s7-sim",
        prefix="CLP_S7_",
        port=102,
        first_octet=127,
        description_template="Controlador Siemens S7 simulado #{index}",
        simulation_key="s7",
        manufacturer="Siemens",
        model="S7-1500 (sim)",
        rack_slot="0,2",
        tags=["s7", "simulador"],
        timeout=3000,
        register_templates=[
            RegisterTemplate(
                name="Temperatura de Processo S7",
                address="DB1.DBW0",
                register_type="db",
                data_type="int16",
                unit="°C",
                description="Temperatura simulada armazenada no DB1 para {plc_name}",
                tag="TEMP_S7",
                alarm={
                    "name": "ALM_{plc_name}_TEMP",
                    "condition_type": "above",
                    "setpoint": 70.0,
                    "deadband": 5.0,
                    "severity": 3,
                    "description": "Alarme de sobretemperatura no CLP S7",
                },
            ),
            RegisterTemplate(
                name="Pressão de Linha S7",
                address="DB1.DBW2",
                register_type="db",
                data_type="int16",
                unit="bar",
                description="Pressão simulada armazenada no DB1 para {plc_name}",
                tag="PRESSAO_S7",
                alarm={
                    "name": "ALM_{plc_name}_PRESSAO",
                    "condition_type": "above",
                    "setpoint": 8.0,
                    "deadband": 1.0,
                    "severity": 2,
                    "description": "Alarme de sobrepressão no CLP S7",
                },
            ),
        ],
    ),
    "opcua": ProtocolConfig(
        protocol="opcua-sim",
        prefix="CLP_OPC_",
        port=4840,
        first_octet=126,
        description_template="Servidor OPC UA simulado #{index}",
        simulation_key="opcua",
        manufacturer="OPC Foundation",
        model="Servidor OPC UA (sim)",
        tags=["opcua", "simulador"],
        timeout=4000,
        register_templates=[
            RegisterTemplate(
                name="Temperatura OPC UA",
                address="ns=2;s=Simulador/{plc_name}/Temperature",
                register_type="node",
                data_type="float",
                unit="°C",
                description="Temperatura publicada via servidor OPC UA simulado",
                tag="TEMP_OPCUA",
                alarm={
                    "name": "ALM_{plc_name}_TEMP_OPCUA",
                    "condition_type": "above",
                    "setpoint": 90.0,
                    "deadband": 10.0,
                    "severity": 4,
                    "description": "Alarme de temperatura alta no nó OPC UA",
                },
            ),
            RegisterTemplate(
                name="Estado da Bomba OPC UA",
                address="ns=2;s=Simulador/{plc_name}/PumpState",
                register_type="node",
                data_type="bool",
                description="Estado lógico da bomba exposto via OPC UA",
                tag="BOMBA_OPCUA",
                alarm={
                    "name": "ALM_{plc_name}_BOMBA",
                    "condition_type": "above",
                    "setpoint": 0.5,
                    "deadband": 0.0,
                    "severity": 1,
                    "description": "Sinaliza quando a bomba está ligada",
                },
            ),
        ],
    ),
    "modbus": ProtocolConfig(
        protocol="modbus-sim",
        prefix="CLP_MODBUS_",
        port=5020,
        first_octet=125,
        description_template="Controlador Modbus TCP simulado #{index}",
        simulation_key="modbus",
        manufacturer="Generic",
        model="Modbus TCP (sim)",
        unit_id=1,
        tags=["modbus", "simulador"],
        timeout=3000,
        register_templates=[
            RegisterTemplate(
                name="Temperatura Modbus",
                address="40001",
                register_type="holding",
                data_type="float",
                unit="°C",
                description="Temperatura de processo simulada via Modbus TCP",
                tag="TEMP_MODBUS",
                alarm={
                    "name": "ALM_{plc_name}_TEMP",
                    "condition_type": "above",
                    "setpoint": 85.0,
                    "deadband": 5.0,
                    "severity": 3,
                    "description": "Alarme de sobretemperatura no CLP Modbus",
                },
            ),
            RegisterTemplate(
                name="Pressão Modbus",
                address="40002",
                register_type="holding",
                data_type="float",
                unit="bar",
                description="Pressão de linha simulada via Modbus TCP",
                tag="PRESSAO_MODBUS",
                alarm={
                    "name": "ALM_{plc_name}_PRESSAO",
                    "condition_type": "above",
                    "setpoint": 10.0,
                    "deadband": 2.0,
                    "severity": 2,
                    "description": "Alarme de sobrepressão no CLP Modbus",
                },
            ),
        ],
    ),
}

# ===========================================================
# FUNÇÕES DE SUPORTE
# ===========================================================
app = create_app()
AlarmRepo = AlarmDefinitionRepo()


def ip_from_index(index: int, *, first_octet: int = 127) -> str:
    n = index - 1
    second = (n // (256 * 256)) % 256
    third = (n // 256) % 256
    fourth = n % 256 + 1
    return f"{first_octet}.{second}.{third}.{fourth}"


def _format_field(value: Optional[object], context: Dict[str, object]) -> Optional[object]:
    if isinstance(value, str):
        return value.format(**context)
    return value


def ensure_register(plc: PLC, template: RegisterTemplate, context: Dict[str, object]) -> Optional[Register]:
    address = str(_format_field(template.address, context))
    register = RegRepo.first_by(plc_id=plc.id, address=address)

    payload = {
        "name": _format_field(template.name, context),
        "description": _format_field(template.description, context),
        "tag": _format_field(template.tag, context),
        "register_type": template.register_type,
        "data_type": template.data_type,
        "unit": template.unit,
        "length": template.length,
        "poll_rate": template.poll_rate,
    }

    if register:
        updated = False
        for key, value in payload.items():
            if value is not None and getattr(register, key) != value:
                setattr(register, key, value)
                updated = True
        if updated:
            RegRepo.update(register, commit=True)
        return register

    new_register = Register(plc_id=plc.id, **payload, address=address, is_active=True)
    return RegRepo.add(new_register, commit=True)


def ensure_alarm(plc: PLC, register: Register, alarm_template: Dict[str, object], context: Dict[str, object]) -> Optional[AlarmDefinition]:
    formatted = {key: _format_field(value, context) for key, value in alarm_template.items()}
    name = formatted.pop("name", f"Alarm {register.name}")
    existing = AlarmRepo.first_by(plc_id=plc.id, register_id=register.id, name=name)
    payload = {k: v for k, v in formatted.items() if v is not None}
    if existing:
        for attr, value in payload.items():
            if getattr(existing, attr) != value:
                setattr(existing, attr, value)
        AlarmRepo.update(existing, commit=True)
        return existing
    alarm = AlarmDefinition(plc_id=plc.id, register_id=register.id, name=name, **payload)
    return AlarmRepo.add(alarm, commit=True)


# ===========================================================
# CONFIGURAÇÃO DE TODOS OS CLPs
# ===========================================================
def setup_single_plc(protocol_key: str, index: int) -> bool:
    config = PROTOCOL_CONFIGS[protocol_key]
    plc_name = f"{config.prefix}{index}"
    plc_ip = ip_from_index(config.ip_offset + index, first_octet=config.first_octet)
    context = {"plc_name": plc_name, "index": index}
    with app.app_context():
        try:
            existing_plc = Plcrepo.first_by(ip_address=plc_ip) or Plcrepo.first_by(name=plc_name)
            if not existing_plc:
                plc = PLC(
                    name=plc_name,
                    description=config.description_template.format(**context),
                    ip_address=plc_ip,
                    protocol=config.protocol,
                    port=config.port,
                    unit_id=config.unit_id,
                    rack_slot=config.rack_slot,
                    is_active=True,
                    polling_interval=config.polling_interval,
                    timeout=config.timeout,
                    manufacturer=config.manufacturer,
                    model=config.model,
                )
                if config.tags:
                    plc.set_tags(config.tags)
                Plcrepo.add(plc, commit=True)
                existing_plc = plc
            else:
                for attr, value in {
                    "description": config.description_template.format(**context),
                    "protocol": config.protocol,
                    "port": config.port,
                    "unit_id": config.unit_id,
                    "rack_slot": config.rack_slot,
                    "polling_interval": config.polling_interval,
                    "timeout": config.timeout,
                    "manufacturer": config.manufacturer,
                    "model": config.model,
                    "is_active": True,
                }.items():
                    setattr(existing_plc, attr, value)
                if config.tags:
                    existing_plc.set_tags(config.tags)
                Plcrepo.update(existing_plc, commit=True)

            registers = []
            for template in config.register_templates:
                reg = ensure_register(existing_plc, template, context)
                if reg:
                    registers.append((reg, template))
                    if config.simulation_key:
                        simulation_registry.next_value(config.simulation_key, reg)

            for reg, template in registers:
                if template.alarm:
                    ensure_alarm(existing_plc, reg, template.alarm, context)

            logger.info("[%s] CLP configurado (%s) com %d registradores.", plc_name, protocol_key, len(registers))
            return True
        except Exception as e:
            logger.exception("[%s] Falha na configuração do CLP: %s", plc_name, e)
            return False


def setup_all_plcs() -> Dict[str, int]:
    simulation_registry.clear()
    resultados = {key: 0 for key in PROTOCOL_CONFIGS}
    for key in PROTOCOL_CONFIGS:
        for idx in range(1, CLPS_POR_PROTOCOLO + 1):
            if setup_single_plc(key, idx):
                resultados[key] += 1
    return resultados


# ===========================================================
# MAIN EXECUÇÃO DIRETA (SEM CLI)
# ===========================================================
if __name__ == "__main__":
    total_esperado = CLPS_POR_PROTOCOLO * len(PROTOCOL_CONFIGS)
    logger.process(f"Iniciando configuração de {CLPS_POR_PROTOCOLO} CLPs para cada protocolo: {', '.join(PROTOCOL_CONFIGS)}")

    inicio = time.time()
    resultados = setup_all_plcs()
    elapsed = time.time() - inicio

    total_criado = sum(resultados.values())
    logger.process(f"{total_criado}/{total_esperado} CLPs configurados em {elapsed:.2f}s.")
    for protocolo, quantidade in resultados.items():
        logger.info("Protocolo %s: %d CLPs ativos.", protocolo, quantidade)

    polling_manager = SimpleManager(app)
    runtime = PollingRuntime(manager=polling_manager)
    with app.app_context():
        runtime.set_enabled(get_polling_enabled())
    register_runtime(app, runtime)
    threading.Thread(target=run_async_polling, args=(app, runtime), daemon=True).start()
    logger.info("Serviço de polling iniciado em background.")

    logger.process("Iniciando servidor Flask em http://0.0.0.0:5000")
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
