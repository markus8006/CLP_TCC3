from src.app import create_app
from src.utils.logs import logger
import threading
from src.simulations.modbus_simulation import start_modbus_simulator, add_register_test_modbus
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.models import PLC
from src.adapters.modbus_adapter import ModbusAdapter
from src.services.client_service import SimpleManager, wait_for_port, example_registers_provider
import time
import asyncio


app = create_app()

HOST = "127.0.0.1"
MOSBUS_PORT = 5020

with app.app_context():
    logger.process("Iniciando simulador Modbus em %s:%s", HOST, MOSBUS_PORT)
    modbus_thread = threading.Thread(
    target=start_modbus_simulator, args=(HOST, MOSBUS_PORT), daemon=True
    )
    modbus_thread.start()
    logger.info("Servidor iniciado")
    logger.process("Adicionando PLC ao banco de dados")
    plc = PLC(name='PLCMod', ip_address='127.0.0.1', protocol='modbus', port=5020, unit_id=1)
    Plcrepo.add(plc)
    logger.process("Adicionando registrador")
    time.sleep(1)
    add_register_test_modbus(plc_name="PLCMod", host="127.0.0.1", port=5020, address=0)
    logger.info("Registrador iniciado")
    time.sleep(1)

    logger.process("Criando adapter")
    print(Plcrepo.first_by(ip_address=HOST).__dict__)
    plc = ModbusAdapter(Plcrepo.first_by(ip_address=HOST))
    

    async def con():
        logger.process("Conectando plc")
        await plc.connect()
        await asyncio.sleep(1)
        logger.process("lendo register")
        teste = await plc.read_register(RegRepo.first_by(plc_id=getattr(Plcrepo.first_by(ip_address=HOST), "id")))
        print(teste)

    async def main():
        mgr = SimpleManager()

        plc_cfg = {
        "ip": "127.0.0.1",
        "port": 5020,
        "unit": 1,
        "vlan": None,
        "poll_interval": 1.0,
        "plc_id": 1,
        }

    # wait for simulator (optional)
        if not wait_for_port(plc_cfg["ip"], plc_cfg["port"], timeout=6.0):
            logger.warning("Modbus server not listening yet at %s:%s - continuing (you may start simulator)", plc_cfg["ip"], plc_cfg["port"])

    # add PLC (starts polling task)
        await mgr.add_plc(plc_cfg, example_registers_provider)

    # let it run for some seconds
        await asyncio.sleep(8)

if __name__ == "__main__":
    asyncio.run(main())


with app.app_context():
    asyncio.run(con())
logger.info("Thread do simulador Modbus iniciada.")


logger.process("Iniciando server")
app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)