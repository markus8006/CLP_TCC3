#!/usr/bin/env python3
# src/jobs/cleanup_old_data.py
"""
Job de limpeza de dados antigos do DataLog.
Executar via cron: 0 3 * * * (3 AM diariamente)

Uso:
    python -m src.jobs.cleanup_old_data
"""

from src.models.Data import DataLog
from src.app import create_app, db
from src.utils.logs import logger
from datetime import datetime

def cleanup_old_datalogs(keep_per_register=30, batch_delete_size=1000):
    """
    Remove registros antigos mantendo apenas os N mais recentes por (plc_id, register_id).
    
    Args:
        keep_per_register: Número de registros a manter por combinação
        batch_delete_size: Tamanho do batch para deletar (evitar timeouts)
    """
    app = create_app()
    with app.app_context():
        start_time = datetime.now()
        total_deleted = 0
        
        logger.info("Iniciando limpeza de DataLogs antigos...")
        
        # Buscar todas combinações únicas de (plc_id, register_id)
        unique_pairs = db.session.query(
            DataLog.plc_id, 
            DataLog.register_id
        ).distinct().all()
        
        logger.info(f"Encontradas {len(unique_pairs)} combinações únicas (plc_id, register_id)")
        
        for idx, (plc_id, register_id) in enumerate(unique_pairs, 1):
            try:
                # Subquery para IDs que devem ser deletados
                subquery = (db.session.query(DataLog.id)
                    .filter_by(plc_id=plc_id, register_id=register_id)
                    .order_by(DataLog.timestamp.desc())
                    .offset(keep_per_register)
                )
                old_ids = [r[0] for r in subquery.all()]
                
                if old_ids:
                    # Deletar em batches para evitar timeout
                    for i in range(0, len(old_ids), batch_delete_size):
                        batch = old_ids[i:i+batch_delete_size]
                        deleted = db.session.query(DataLog).filter(
                            DataLog.id.in_(batch)
                        ).delete(synchronize_session=False)
                        db.session.commit()
                        total_deleted += deleted
                    
                    logger.debug(f"[{idx}/{len(unique_pairs)}] PLC {plc_id}, Reg {register_id}: {len(old_ids)} registros removidos")
            
            except Exception as e:
                logger.exception(f"Erro ao limpar plc_id={plc_id}, register_id={register_id}: {e}")
                db.session.rollback()
                continue
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Limpeza concluída! {total_deleted} registros deletados em {elapsed:.2f}s")
        
        return total_deleted

if __name__ == "__main__":
    cleanup_old_datalogs()
