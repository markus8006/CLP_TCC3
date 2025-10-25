"""
Repositórios genéricos para o projeto SCADA.

Coloque este arquivo em `src/repos/repositories.py` ou divida em vários módulos.

Funcionalidades principais:
- BaseRepo: operações comuns (get, list, add, update, delete, filter)
- PLCRepo, RegisterRepo, OrganizationRepo, AlarmDefinitionRepo, AlarmRepo, DataLogRepo
- DataLogRepo tem `bulk_insert()` para inserir muitos pontos rapidamente

"""
from typing import Type, List, Optional, Dict, Any, Iterable
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from src.app import db
from src.utils.logs import logger

class BaseRepo:
    """Repositório base genérico.

    Params
    ------
    model: classe ORM (ex: PLC)
    session: SQLAlchemy session (opcional) — por padrão usa `db.session`
    """

    def __init__(self, model: Type[Any], session: Optional[Session] = None):
        self.model = model
        self.session = session or db.session

    def get(self, id: int) -> Optional[Any]:
        try:
            return self.session.query(self.model).get(id)
        except SQLAlchemyError:
            logger.exception("Erro get %s id=%s", getattr(self.model, '__name__', str(self.model)), id)
            return None

    def list_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Any]:
        q = self.session.query(self.model).order_by(self.model.id)
        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(limit)
        try:
            return q.all()
        except SQLAlchemyError:
            logger.exception("Erro list_all %s", getattr(self.model, '__name__', str(self.model)))
            return []

    def find_by(self, **filters) -> List[Any]:
        try:
            return self.session.query(self.model).filter_by(**filters).all()
        except SQLAlchemyError:
            logger.exception("Erro find_by %s filters=%s", getattr(self.model, '__name__', str(self.model)), filters)
            return []

    def first_by(self, **filters) -> Optional[Any]:
        try:
            return self.session.query(self.model).filter_by(**filters).first()
        except SQLAlchemyError:
            logger.exception("Erro first_by %s filters=%s", getattr(self.model, '__name__', str(self.model)), filters)
            return None

    def add(self, obj: Any, commit: bool = True) -> Any:
        try:
            self.session.add(obj)
            if commit:
                logger.info("CLP ja cadastrado, atualizando se aplicavél")
                self.session.commit()
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", getattr(self.model, '__name__', str(self.model)))
            raise

    def update(self, obj: Any, commit: bool = True) -> Any:
        try:
            merged = self.session.merge(obj)
            if commit:
                self.session.commit()
            return merged
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao atualizar %s", getattr(self.model, '__name__', str(self.model)))
            raise

    def delete(self, obj: Any, commit: bool = True) -> bool:
        try:
            self.session.delete(obj)
            if commit:
                self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao deletar %s", getattr(self.model, '__name__', str(self.model)))
            raise

    def delete_by_id(self, id: int, commit: bool = True) -> bool:
        obj = self.get(id)
        if not obj:
            return False
        return self.delete(obj, commit=commit)
    
    def exist(self, **filters : Any) -> bool:
        try:
            return True if self.find_by(**filters) != [] else False
        except:
            return False



# ===== Exemplo de uso (usuário: adapte ao seu app) =====
# from src.repos.repositories import PLCRepo, RegisterRepo, DataLogRepo
# plc_repo = PLCRepo()
# new_plc = PLC(name='PLC1', ip_address='10.0.0.1', protocol='modbus', port=502)
# plc_repo.add(new_plc)

# register_repo = RegisterRepo()
# r = Register(plc_id=new_plc.id, name='Temp', address='0', register_type='holding', data_type='int16')
# register_repo.add(r)

# datalog_repo = DataLogRepo()
# datalog_repo.bulk_insert([{'plc_id': new_plc.id, 'register_id': r.id, 'raw_value': '123', 'value_float': 12.3}])


# Fim do arquivo
