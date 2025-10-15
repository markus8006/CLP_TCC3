import asyncio
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSequentialDataBlock
from pymodbus.server import StartAsyncTcpServer
from pymodbus.device import ModbusDeviceIdentification
from src.utils.logs import logger
from typing import Optional

from  src.models import PLC
from src.models import Register
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo


from src.app import db
from src.models import Register




import threading
import os


async def start_modbus_async(host: str = "127.0.0.1", port: int = 5020):
    """
    Inicia um servidor Modbus TCP assíncrono com 2 slaves de exemplo (unit id 1 e 2).
    Bloqueia (fica rodando) até ser cancelado.
    """
    # Cria blocos de dados (addresses a partir de 0)
    hr_block_1 = ModbusSequentialDataBlock(0, [11] * 10)                 # slave 1
    hr_block_2 = ModbusSequentialDataBlock(0, [100 + i for i in range(5)])  # slave 2

    # Cada slave precisa ser um ModbusSlaveContext
    slave1 = ModbusSlaveContext(hr=hr_block_1)
    slave2 = ModbusSlaveContext(hr=hr_block_2)

    # Cria o contexto do servidor com os slaves (unit ids)
    context = ModbusServerContext(slaves={1: slave1, 2: slave2}, single=False)

    identity = ModbusDeviceIdentification(
        info_name={
            "VendorName": "Simulated CLP",
            "ProductCode": "SIM",
            "ProductName": "SimCLP",
            "MajorMinorRevision": "1.0"
        }
    )

    logger.process("Iniciando servidor Modbus TCP em %s:%s", host, port)
    # StartAsyncTcpServer é coroutine que roda o servidor (bloqueia até cancelamento)
    await StartAsyncTcpServer(context=context, identity=identity, address=(host, port))


def start_modbus_simulator(host: str = "127.0.0.1", port: int = 5020):
    """
    Função de entrada que pode ser chamada dentro de uma thread ou processo.
    StartAsyncTcpServer é async, então rodamos com asyncio.run()
    """
    try:
        asyncio.run(start_modbus_async(host, port))
    except Exception as e:
        logger.exception("Erro iniciando simulador Modbus: %s", e)



def add_register_test_modbus(
    plc_name: str = "CLP De Teste",
    host: str = "127.0.0.1",
    port: int = 5020,
    unit_id: int = 1,
    address: int = 0,
    register_name: Optional[str] = None,
    commit: bool = True
):
    """
    Cria um Register no banco apontando para um PLC (cria o PLC se necessário).
    - plc_name: nome do plc usado na busca/criação
    - host/port/unit_id: usados para criar o PLC (ip_address/port/unit_id)
    - address: endereço do registrador (int) -> será salvo como string para compatibilidade com o model
    - register_name: nome do registrador (se None usa 'Temperatura Teste')
    - commit: se True dá commit na sessão
    Retorna a instância do Register criada.
    """
    if register_name is None:
        register_name = "Temperatura Teste"


    from src.app import db

    # Procurar PLC pelo nome; se não existir, cria com dados mínimos compatíveis com o seu model
    plc = db.session.query(PLC).filter_by(name=plc_name).first()
    if not plc:
        logger.info("PLC não encontrado com name=%s. Criando PLC de teste (ip=%s port=%s unit=%s).", plc_name, host, port, unit_id)
        # Tentar popular campos mínimos: ip_address, protocol, port, vlan_id (opcional), name
        try:
            plc_kwargs = {
                "name": plc_name,
                "ip_address": host,
                "protocol": "modbus",
                "port": port,
                "is_active": True,
            }
            # se o modelo tiver unit_id/serial_number etc, deixamos como opcionais; SQLAlchemy vai ignorar chaves inválidas?
            # portanto construir a instância respeitando o __init__ do model (padrão do Flask-SQLAlchemy aceita kw).
            plc = PLC(**plc_kwargs)
            Plcrepo.add(plc)
            if commit:
                db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Falha criando PLC de teste no DB")
            raise

    # agora cria Register compatível com seu 
    addr_value = str(address)
    try:
        logger.info("DEBUG: antes do RegRepo.first_by() - thread=%s pid=%s", threading.current_thread().name, os.getpid())
        existing = RegRepo.first_by(plc_id=plc.id, address=addr_value)
        
        # converter address para string se o model espera string
        if existing:
            logger.info("registraor achado")
            # atualiza campos no objeto carregado do DB (não crie nova instância)
            existing.name = register_name
            existing.register_type = "holding"
            existing.data_type = "int16"
            existing.scale_factor = 1.0
            existing.offset = 0.0
            existing.unit = "°C"
            existing.is_active = True
            RegRepo.update(existing)
            reg = existing
            logger.info("%s atualizado", reg)
        else:
            reg = Register(
                plc_id=plc.id,
                name=register_name,
                address=addr_value,
                register_type="holding",
                data_type="int16",
                scale_factor=1.0,
                offset=0.0,
                unit="°C",
                is_active=True
            )
            RegRepo.add(reg)
            logger.info("%s adicionado", reg)

        if commit:
            db.session.commit()
        logger.info("Registrador salvo: plc_id=%s reg_id=%s addr=%s", plc.id, reg.id, addr_value)
        return reg
    except Exception:
        db.session.rollback()
        logger.exception("Erro ao salvar registrador de teste")
        raise