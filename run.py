import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.app import create_app
from src.models import PLC
from src.models.Alarms import AlarmDefinition
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Alarms_repository import AlarmDefinitionRepo
from src.manager.client_polling_manager import SimpleManager, wait_for_port
from src.simulations.modbus_simulation import add_register_test_modbus, start_modbus_simulator
from src.services.client_polling_service import run_async_polling
from src.utils.logs import logger
import logging

# --- Configurações ---
HOST = "127.0.0.1"
MODBUS_PORT = 5020
NUM_CLPS = 30
MAX_THREADS = 16  # controla paralelismo
# --- Fim Configurações ---

# logger.setLevel(logging.INFO)

app = create_app()
AlarmRepo = AlarmDefinitionRepo()

def ip_from_index(index: int, first_octet: int = 127) -> str:
    if index < 1:
        raise ValueError("index deve ser >= 1")
    n = index - 1
    second = (n // (256*256)) % 256
    third = (n // 256) % 256
    fourth = n % 256 + 1
    return f"{first_octet}.{second}.{third}.{fourth}"

# -----------------------
# Função que cria 1 CLP
# -----------------------
def setup_single_clp(index: int, app):
    with app.app_context():
        plc_name = f"PLCMod{index}"
        plc_ip = ip_from_index(index)
        logger.debug(f"[{plc_name}] Iniciando criação...")

        try:
            # Start simulador em thread separada
            t = threading.Thread(
                target=start_modbus_simulator,
                args=(plc_ip, MODBUS_PORT),
                daemon=True
            )
            t.start()
        except Exception as e:
            logger.error(f"[{plc_name}] Erro ao iniciar simulador: {e}")
            return False

        # Espera porta abrir (curto timeout)
        try:
            if not wait_for_port(plc_ip, MODBUS_PORT, timeout=2.0):
                logger.warning(f"[{plc_name}] Modbus não respondeu no timeout.")
        except Exception as e:
            logger.warning(f"[{plc_name}] wait_for_port falhou: {e}")

        # Criação no banco
        try:
            existing_plc = Plcrepo.first_by(ip_address=plc_ip) or Plcrepo.first_by(name=plc_name)
            if not existing_plc:
                plc_to_add = PLC(
                    name=plc_name,
                    ip_address=plc_ip,
                    protocol="modbus",
                    port=MODBUS_PORT,
                    unit_id=1,
                    is_active=True
                )
                Plcrepo.add(plc_to_add, commit=True)
                existing_plc = Plcrepo.first_by(ip_address=plc_ip)
            logger.info(f"[{plc_name}] Criado com sucesso (id={existing_plc.id})")
        except Exception as e:
            logger.error(f"[{plc_name}] Erro ao criar PLC: {e}")
            return False

        # Registers
        try:
            reg0 = add_register_test_modbus(plc_name=plc_name, host=plc_ip, port=MODBUS_PORT, address=0, register_name="Temperatura Teste")
            reg1 = add_register_test_modbus(plc_name=plc_name, host=plc_ip, port=MODBUS_PORT, address=1, register_name="CALOR")
        except Exception as e:
            logger.error(f"[{plc_name}] Erro ao criar registradores: {e}")
            reg0 = reg1 = None

        # Busca se não retornou
        reg0 = reg0 or RegRepo.first_by(plc_id=existing_plc.id, address=0)
        reg1 = reg1 or RegRepo.first_by(plc_id=existing_plc.id, address=1)

        # Alarme defs
        try:
            if reg0 and not AlarmRepo.first_by(plc_id=existing_plc.id, register_id=reg0.id):
                AlarmRepo.add(AlarmDefinition(plc_id=existing_plc.id, register_id=reg0.id,
                                              name="alarmTeste_10", setpoint=10), commit=True)
            if reg1 and not AlarmRepo.first_by(plc_id=existing_plc.id, register_id=reg1.id):
                AlarmRepo.add(AlarmDefinition(plc_id=existing_plc.id, register_id=reg1.id,
                                              name="alarmTeste_12", setpoint=12), commit=True)
        except Exception as e:
            logger.error(f"[{plc_name}] Erro ao criar AlarmDefinition: {e}")

        logger.info(f"[{plc_name}] Configuração concluída.")
        return True

# ------------------------
# Loop paralelizado
# ------------------------
if __name__ == "__main__":
    with app.app_context():
        logger.process(f"Iniciando configuração paralela de {NUM_CLPS} CLPs...")

        start_time = time.time()
        created = 0

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [executor.submit(setup_single_clp, i, app) for i in range(1, NUM_CLPS + 1)]
            for future in as_completed(futures):
                if future.result():
                    created += 1

        elapsed = time.time() - start_time
        logger.process(f"{created}/{NUM_CLPS} CLPs criados em {elapsed:.2f}s com {MAX_THREADS} threads.")

        # Serviço de polling em background
        polling_manager = SimpleManager(app)
        threading.Thread(
            target=run_async_polling, args=(app, polling_manager), daemon=True
        ).start()
        logger.info("Serviço de polling rodando em background.")

    logger.process("Iniciando servidor Flask em http://0.0.0.0:5000")
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
