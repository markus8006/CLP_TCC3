
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

            # Limpa registros antigos por plc_id e register_id, mantendo no máximo 30
            keys = set((rec['plc_id'], rec['register_id']) for rec in records)
            for plc_id, register_id in keys:
                subquery = (self.session.query(self.model.id)
                                    .filter_by(plc_id=plc_id, register_id=register_id)
                                    .order_by(self.model.timestamp.desc())
                                    .offset(30)
                                    )
                old_ids = [r[0] for r in subquery.all()]
                if old_ids:
                    self.session.query(self.model).filter(self.model.id.in_(old_ids)).delete(synchronize_session=False)
                    if commit:
                        self.session.commit()
            return inserted
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro bulk_insert DataLog")
            raise
