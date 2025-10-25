# run.py
import threading
import time
from src.app import create_app
from src.models import PLC
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Alarms_repository import AlarmDefinitionRepo
from src.models.Alarms import AlarmDefinition
from src.manager.client_polling_manager import SimpleManager, wait_for_port
from src.simulations.modbus_simulation import add_register_test_modbus, start_modbus_simulator
from src.services.client_polling_service import run_async_polling
from src.utils.logs import logger
import logging
from flask_sqlalchemy import SQLAlchemy

# Instância do repo de definições de alarme
AlarmRepo = AlarmDefinitionRepo()

# --- Configurações ---
HOST = "127.0.0.1"     # bind host dos simuladores (usado apenas para start modbus, veja observações)
MODBUS_PORT = 5020     # porta base para todos (pode ser mantida igual se cada simulador bind em IP diferente)
NUM_CLPS = 2       # quantos PLCs quer criar
# --- Fim Configurações ---

app = create_app()
# logger.setLevel(logging.INFO)

def ip_from_index(index: int, first_octet: int = 127) -> str:
    """
    Gera um IP sequencial para index >= 1 no bloco first_octet.x.y.z.
    Mapeamento: index=1 -> first_octet.0.0.1, index=256 -> first_octet.0.1.0, etc.
    Suporta até ~16 milhões (index <= 16777215).
    """
    if index < 1:
        raise ValueError("index deve ser >= 1")
    n = index - 1
    second = (n // (256*256)) % 256
    third = (n // 256) % 256
    fourth = n % 256 + 1
    return f"{first_octet}.{second}.{third}.{fourth}"

if __name__ == "__main__":
    with app.app_context():
        logger.process(f"Configurando {NUM_CLPS} PLCs de teste no banco de dados...")

        # pequena defesa: limite prático (você pode ajustar/remover)
        MAX_SUPPORTED = 16_777_215
        if NUM_CLPS > MAX_SUPPORTED:
            logger.warning(f"NUM_CLPS muito grande ({NUM_CLPS}), limite prático = {MAX_SUPPORTED}. Truncando.")
            effective_num = MAX_SUPPORTED
        else:
            effective_num = NUM_CLPS

        # loop de criação
        for i in range(1, effective_num + 1):
            plc_name = f"PLCMod{i}"
            plc_ip = ip_from_index(i, first_octet=127)

            # inicia um simulador ligado ao ip gerado (se seu start_modbus_simulator fizer bind por IP)
            try:
                t = threading.Thread(
                    target=start_modbus_simulator, args=(plc_ip, MODBUS_PORT), daemon=True
                )
                t.start()
            except Exception as e:
                logger.error(f"Erro ao iniciar simulador para {plc_ip}:{MODBUS_PORT}: {e}")
                # não aborta todo loop, apenas registra e continua
                continue

            # aguarda porta (curto timeout). se não der, apenas loga e continua
            try:
                if not wait_for_port(plc_ip, MODBUS_PORT, timeout=3.0):
                    logger.warning(f"Simulador Modbus em {plc_ip}:{MODBUS_PORT} não respondeu no timeout.")
                else:
                    logger.info(f"Simulador Modbus iniciado para {plc_name} em {plc_ip}:{MODBUS_PORT}")
            except Exception as e:
                logger.warning(f"wait_for_port falhou para {plc_ip}:{MODBUS_PORT}: {e}")

            # cria PLC no DB (se não existir)
            existing_plc = Plcrepo.first_by(ip_address=plc_ip) or Plcrepo.first_by(name=plc_name)
            if not existing_plc:
                try:
                    plc_to_add = PLC(
                        name=plc_name,
                        ip_address=plc_ip,
                        protocol='modbus',
                        port=MODBUS_PORT,
                        unit_id=1,
                        is_active=True
                    )
                    Plcrepo.add(plc_to_add, commit=True)
                    # reconsulta para garantir id preenchido
                    existing_plc = Plcrepo.first_by(ip_address=plc_ip) or Plcrepo.first_by(name=plc_name)
                    logger.info(f"PLC criado: {plc_name} ({plc_ip}) id={getattr(existing_plc,'id',None)}")
                except Exception as e:
                    logger.error(f"Erro ao criar PLC {plc_name} ({plc_ip}): {e}")
                    continue

            # cria registradores de teste (add_register_test_modbus verifica e garante plc_id)
            try:
                reg0 = add_register_test_modbus(plc_name=plc_name, host=plc_ip, port=MODBUS_PORT, address=0, register_name="Temperatura Teste")
                reg1 = add_register_test_modbus(plc_name=plc_name, host=plc_ip, port=MODBUS_PORT, address=1, register_name="CALOR")
            except Exception as e:
                logger.error(f"Erro ao adicionar registers para {plc_name}: {e}")
                reg0 = reg1 = None

            # busca registros (caso helper não retorne)
            if not reg0:
                try:
                    reg0 = RegRepo.first_by(plc_id=existing_plc.id, address=0)
                except Exception:
                    reg0 = None
            if not reg1:
                try:
                    reg1 = RegRepo.first_by(plc_id=existing_plc.id, address=1)
                except Exception:
                    reg1 = None

            # cria/altera definitions de alarme (setpoint 10 e 12)
            if reg0:
                try:
                    exists0 = AlarmRepo.first_by(plc_id=existing_plc.id, register_id=reg0.id)
                    if not exists0:
                        AlarmRepo.add(AlarmDefinition(plc_id=existing_plc.id, register_id=reg0.id, name="alarmTeste_10", setpoint=10), commit=True)
                except Exception as e:
                    logger.error(f"Erro ao criar AlarmDefinition para {plc_name} reg0: {e}")

            if reg1:
                try:
                    exists1 = AlarmRepo.first_by(plc_id=existing_plc.id, register_id=reg1.id)
                    if not exists1:
                        AlarmRepo.add(AlarmDefinition(plc_id=existing_plc.id, register_id=reg1.id, name="alarmTeste_12", setpoint=12), commit=True)
                except Exception as e:
                    logger.error(f"Erro ao criar AlarmDefinition para {plc_name} reg1: {e}")

            logger.info(f"PLC {plc_name} ({plc_ip}) configurado com registradores e alarmes.")
            # throttle pequeno para evitar sobrecarga instantânea do sistema
            time.sleep(0.01)

        logger.info("Todos PLCs de teste configurados (loop concluído).")

        # ETAPA 3: Iniciar o serviço de polling em background
        polling_manager = SimpleManager(app)
        polling_service_thread = threading.Thread(
            target=run_async_polling,
            args=(app, polling_manager),
            daemon=True
        )
        polling_service_thread.start()
        logger.info("Serviço de polling rodando em background.")

    # ETAPA 4: Iniciar o Servidor Web Flask (Aplicação Principal)
    logger.process("Iniciando servidor Flask em http://0.0.0.0:5000")
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.CRITICAL)

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
