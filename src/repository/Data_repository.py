
#src/repository/Data_repository.py
from src.models.Data import DataLog
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Iterable



class DataLogRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if DataLog is None:
            raise RuntimeError("Modelo DataLog não encontrado. Ajuste os imports.")
        super().__init__(DataLog, session=session)

    def list_recent(self, plc_id: int, register_id: int, limit: int = 100) -> List[DataLog]:
        q = self.session.query(self.model).filter(
            self.model.plc_id == plc_id,
            self.model.register_id == register_id
        ).order_by(self.model.timestamp.desc()).limit(limit)
        try:
            return q.all()
        except SQLAlchemyError:
            logger.exception("Erro list_recent datalog plc=%s reg=%s", plc_id, register_id)
            return []

    def bulk_insert(self, records: Iterable[Dict[str, Any]], commit: bool = True, batch_size: int = 5000) -> int:
        """Versão otimizada do bulk_insert com menos queries"""
        if not records:
            return 0
    
        records_list = list(records)
        inserted = 0
    
        try:
        # Inserção em lotes maiores usando bulk_insert_mappings
            for i in range(0, len(records_list), batch_size):
                batch = records_list[i:i + batch_size]
                self.session.bulk_insert_mappings(self.model, batch)
                inserted += len(batch)
        
            if commit:
                self.session.commit()
        
        # Limpeza otimizada - uma query CTE em vez de loop
            self._cleanup_old_records_optimized(records_list)
        
            return inserted
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro bulk_insert_optimized DataLog")
            raise

    def _cleanup_old_records_optimized(self, records):
        """Limpeza otimizada usando window functions"""
        from sqlalchemy import text
    
        cleanup_sql = """
    WITH ranked_records AS (
        SELECT id, 
               ROW_NUMBER() OVER (
                   PARTITION BY plc_id, register_id 
                   ORDER BY timestamp DESC
               ) as rn
        FROM data_log 
        WHERE (plc_id, register_id) IN :keys
    )
    DELETE FROM data_log 
    WHERE id IN (SELECT id FROM ranked_records WHERE rn > 30)
    """
    
        keys = set((rec['plc_id'], rec['register_id']) for rec in records)
        if keys:
            self.session.execute(text(cleanup_sql), {'keys': tuple(keys)})



DataRepo = DataLogRepo()