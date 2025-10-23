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
    
    def get_by_register_id(self, register_id: int) -> Optional[AlarmDefinition]:
        return self.first_by(register_id=register_id, is_active=True)

    def list_by_plc_and_register(self, plc_id: int, register_id: int) -> List[AlarmDefinition]:
        return self.find_by(plc_id=plc_id, register_id=register_id, is_active=True)
    
    def get_active_by_definition(self, alarm_definition_id: int) -> Optional[Alarm]:
        return self.first_by(alarm_definition_id=alarm_definition_id, state='ACTIVE')




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