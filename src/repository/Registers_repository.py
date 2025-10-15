from src.models.PLCs import Organization
from src.models.Registers import Register
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from sqlalchemy.exc import SQLAlchemyError



class RegisterRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if Register is None:
            raise RuntimeError("Modelo Register não encontrado. Ajuste os imports.")
        super().__init__(Register, session=session)

    def list_by_plc(self, plc_id: int) -> List[Register]:
        return self.find_by(plc_id=plc_id)
    
    def add(self, obj: Any, commit: bool = True) -> Any:
        try:
            # Use filtros relevantes para saber se já existe
            exists = self.exist(
                plc_id=obj.plc_id,
                address=obj.address
            )
            if not exists:
                result = super().add(obj, commit=commit)
                logger.info(f"register {obj} adicionado")
            else:
                result = self.update(obj, commit=commit)
                logger.info(f"register {obj} atualizado")
            return result
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", getattr(self.model, '__name__', str(self.model)))
            raise
    def get_registers_for_plc(self, plc_id: int):
        """
    Esta função busca os registradores para um CLP específico.
    É o "provider" que o ActivePLCPoller usará.
        """
        # LOG DE DIAGNÓSTICO:
        logger.debug(f"Buscando registradores para o plc_id: {plc_id}")
        
        # Filtros que estamos usando na busca
        filters = {'plc_id': plc_id, 'is_active': True}
        
        registers_found = self.find_by(**filters)
        
        # LOG DE DIAGNÓSTICO:
        if registers_found:
            logger.info(f"Encontrados {len(registers_found)} registradores para o plc_id: {plc_id}")
        else:
            # Este é o log que você estava vendo, mas agora com mais contexto.
            logger.warning(f"Nenhum registrador ativo encontrado para o plc_id: {plc_id} usando os filtros: {filters}")
            
        return registers_found



class OrganizationRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if Organization is None:
            raise RuntimeError("Modelo Organization não encontrado. Ajuste os imports.")
        super().__init__(Organization, session=session)

    def get_children(self, org_id: int) -> List[Organization]:
        org = self.get(org_id)
        if not org:
            return []
        return list(org.children)
    
RegRepo = RegisterRepo()