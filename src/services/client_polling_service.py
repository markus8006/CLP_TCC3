from src.utils.logs import logger
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
import asyncio
from typing import Any

# src/services/client_polling_service.py

# ... (imports) ...

# A função agora recebe o 'manager' que deve usar
async def start_polling_service(app, manager: Any):
    logger.process("Iniciando serviço de polling...")
    with app.app_context():
        active_plcs = Plcrepo.find_by(is_active=True)
        logger.info(f"Encontrados {len(active_plcs)} CLPs ativos para monitorar.")
        for plc in active_plcs:
            # Usa o 'manager' que foi passado como argumento
            await manager.add_plc(plc, lambda plc_id=plc.id: RegRepo.get_registers_for_plc(plc_id))

async def main_async(app, manager: Any):
    await start_polling_service(app, manager)
    while True:
        await asyncio.sleep(3600)

# A função de entrada agora também recebe o 'manager'
def run_async_polling(app, manager: Any):
    asyncio.run(main_async(app, manager))