# run.py
import threading
from src.app import create_app
from src.models import PLC
from src.repository.PLC_repository import Plcrepo
# Importa a CLASSE, não uma instância global
from src.manager.client_polling_manager import SimpleManager, wait_for_port
from src.simulations.modbus_simulation import (add_register_test_modbus,
                                                start_modbus_simulator)
from src.utils.logs import logger
from src.models.Alarms import AlarmDefinition
from src.repository.Alarms_repository import AlarmDefinitionRepo
from src.repository.Registers_repository import RegRepo
from src.models.Alarms import AlarmDefinition
from src.services.client_polling_service import run_async_polling


AlarmRepo = AlarmDefinitionRepo()



# --- Configurações ---
HOST = "127.0.0.1"
MODBUS_PORT = 5020

# --- Cria a Aplicação Flask ---
app = create_app()


# --- Inicialização e Execução ---
if __name__ == "__main__":
    with app.app_context():
        # ETAPA 1: Iniciar os CLPs Simulados para teste
        logger.process(f"Iniciando simuladores Modbus...")
        
        # Simulador para 127.0.0.1
        modbus_thread_1 = threading.Thread(
            target=start_modbus_simulator, args=(HOST, MODBUS_PORT), daemon=True
        )
        modbus_thread_1.start()

        # Simulador para 127.0.0.2
        modbus_thread_2 = threading.Thread(
            target=start_modbus_simulator, args=("127.0.0.2", MODBUS_PORT), daemon=True
        )
        modbus_thread_2.start()

        # Aguarda o primeiro simulador ficar pronto para continuar
        if not wait_for_port(HOST, MODBUS_PORT, timeout=5.0):
            logger.error(f"Simulador Modbus em {HOST}:{MODBUS_PORT} não iniciou. Abortando.")
            exit(1)
        logger.info("Simuladores Modbus iniciados com sucesso.")

        # ETAPA 2: Popular o banco de dados com dados de teste, se necessário
        logger.process("Configurando dados de teste no banco de dados...")
        
        # Garante que o PLC 'PLCMod' existe
        if not Plcrepo.first_by(name='PLCMod'):
            logger.info("PLC 'PLCMod' não encontrado, criando um novo...")
            plc_to_add = PLC(name='PLCMod', ip_address='127.0.0.1', protocol='modbus', port=5020, unit_id=1, is_active=True)
            Plcrepo.add(plc_to_add, commit=True)
            add_register_test_modbus(plc_name="PLCMod", host="127.0.0.1", port=5020, address=0)

        # Garante que o PLC 'PLCMod2' existe
        if not Plcrepo.first_by(name='PLCMod2'):
            logger.info("PLC 'PLCMod2' não encontrado, criando um novo...")
            plc_to_add_2 = PLC(name='PLCMod2', ip_address='127.0.0.2', protocol='modbus', port=5020, unit_id=1, is_active=True)
            Plcrepo.add(plc_to_add_2, commit=True)
            add_register_test_modbus(plc_name="PLCMod2", host="127.0.0.2", port=5020, address=0)
        
        logger.info("Dados de teste configurados.")


        #cria o alarm

        exists = AlarmRepo.first_by(
            plc_id = Plcrepo.first_by(ip_address="127.0.0.1").id,
            register_id = RegRepo.first_by(plc_id=Plcrepo.first_by(ip_address="127.0.0.1").id).id,
        )
        print(exists)
        if not exists:
            alarm = AlarmDefinition(
                plc_id = Plcrepo.first_by(ip_address="127.0.0.1").id,
                register_id = RegRepo.first_by(plc_id=Plcrepo.first_by(ip_address="127.0.0.1").id).id,
                name = "alarmTeste",
                setpoint = 10
            )
            AlarmRepo.add(alarm)

    # ETAPA 3: Iniciar o serviço de polling em background
    
    # 3.1. Cria a instância única do gerente de polling
        polling_manager = SimpleManager(app)
    
    #3.2. Inicia a thread do serviço, injetando o app e o gerente
        polling_service_thread = threading.Thread(
        target=run_async_polling,
        args=(app, polling_manager),  # Passa o gerente como argumento
        daemon=True
        )
        polling_service_thread.start()
        logger.info("Serviço de polling rodando em background.")



    # ETAPA 4: Iniciar o Servidor Web Flask (Aplicação Principal)
    logger.process("Iniciando servidor Flask em http://0.0.0.0:5000")
    # use_reloader=False é importante ao rodar serviços em threads
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)