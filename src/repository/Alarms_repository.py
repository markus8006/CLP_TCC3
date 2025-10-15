from src.models.Alarms import AlarmDefinition, Alarm
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Optional, List

class AlarmDefinitionRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if AlarmDefinition is None:
            raise RuntimeError("Modelo AlarmDefinition não encontrado. Ajuste os imports.")
        super().__init__(AlarmDefinition, session=session)

    def list_by_plc(self, plc_id: int) -> List[AlarmDefinition]:
        return self.find_by(plc_id=plc_id)


class AlarmRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if Alarm is None:
            raise RuntimeError("Modelo Alarm não encontrado. Ajuste os imports.")
        super().__init__(Alarm, session=session)

    def list_active(self, limit: Optional[int] = None) -> List[Alarm]:
        q = self.session.query(self.model).filter(self.model.state == 'ACTIVE').order_by(self.model.triggered_at.desc())
        if limit:
            q = q.limit(limit)
        try:
            return q.all()
        except SQLAlchemyError:
            logger.exception("Erro list_active alarms")
            return []