from src.models.PLCs import PLC
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from src.app import db
from typing import Iterable, Optional, Any



class PLCRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        if PLC is None:
            raise RuntimeError("Modelo PLC não encontrado. Ajuste os imports em src/repos/repositories.py")
        super().__init__(PLC, session=session)

    def get_by_ip(self, ip_address: str, vlan_id: Optional[int] = None) -> Optional[PLC]:
        q = self.session.query(self.model).filter(self.model.ip_address == ip_address)
        if vlan_id is not None:
            q = q.filter(self.model.vlan_id == vlan_id)
        try:
            return q.first()
        except SQLAlchemyError:
            logger.exception("Erro get_by_ip %s vlan=%s", ip_address, vlan_id)
            return None

    def delete_by_ip(self, ip_address: str, vlan_id: Optional[int] = None, commit: bool = True) -> bool:
        plc = self.get_by_ip(ip_address, vlan_id)
        if not plc:
            return False
        return self.delete(plc, commit=commit)

    def upsert_by_ip(self, plc_obj: PLC, commit: bool = True) -> PLC:
        """Insere ou atualiza PLC baseado em ip + vlan_id."""
        existing = self.get_by_ip(plc_obj.ip_address, getattr(plc_obj, 'vlan_id', None))
        if existing:
            # merge fields (exemplo simples — ajuste conforme suas regras)
            for attr in ['name', 'description', 'protocol', 'port', 'unit_id', 'rack_slot', 'is_active']:
                if hasattr(plc_obj, attr):
                    setattr(existing, attr, getattr(plc_obj, attr))
            return self.update(existing, commit=commit)
        else:
            return self.add(plc_obj, commit=commit)
        

    def add(self, obj: Any, commit: bool = True) -> Any:
        try:
            if not self.find_by(ip_address=obj.ip_address, vlan_id=obj.vlan_id, mac_address=obj.mac_address):
                logger.info("add clp")
                self.session.add(obj)
            else:
                logger.info("CLP já cadastrado, atualizando se aplicável")
                self.update(obj)
            if commit:
                self.session.commit()
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", getattr(self.model, '__name__', str(self.model)))
            raise

    def update_tags(self, plc: PLC, tags: Iterable[str], commit: bool = True) -> PLC:
        """Actualiza a lista de tags normalizada para um CLP."""
        try:
            plc.set_tags(tags)
            if commit:
                self.session.commit()
            else:
                self.session.flush()
            return plc
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao actualizar tags do PLC %s", plc.id if plc else "desconhecido")
            raise
    
    

Plcrepo = PLCRepo()