
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

    def bulk_insert(self, records: Iterable[Dict[str, Any]], commit: bool = True, batch_size: int = 1000) -> int:
        """Insere muitos registros de uma vez.

        records: iterável de dicionários compatíveis com o modelo DataLog (keys: plc_id, register_id, timestamp, raw_value, value_float...)
        Retorna número de registros inseridos (apenas tentativa).
        """
        objs = []
        inserted = 0
        try:
            for rec in records:
                objs.append(self.model(**rec))
                if len(objs) >= batch_size:
                    self.session.bulk_save_objects(objs)
                    if commit:
                        self.session.commit()
                    inserted += len(objs)
                    objs = []
            if objs:
                self.session.bulk_save_objects(objs)
                if commit:
                    self.session.commit()
                inserted += len(objs)
            return inserted
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro bulk_insert DataLog")
            raise