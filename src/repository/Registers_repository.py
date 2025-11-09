"""Repositórios para registradores e organizações."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.PLCs import Organization
from src.models.Registers import Register
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger


class RegisterRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None) -> None:
        if Register is None:
            raise RuntimeError("Modelo Register não encontrado. Ajuste os imports.")
        super().__init__(Register, session=session)

    def list_by_plc(self, plc_id: int) -> List[Register]:
        return self.find_by(plc_id=plc_id)

    def add(self, obj: Any, commit: bool = True) -> Any:
        try:
            existing = self.first_by(plc_id=obj.plc_id, address=obj.address)
            if existing:
                logger.info("Registro %s já existe — actualizando dados.", existing.id)
                for attr in [
                    "name",
                    "register_type",
                    "data_type",
                    "unit",
                    "poll_rate",
                    "is_active",
                ]:
                    if hasattr(obj, attr):
                        setattr(existing, attr, getattr(obj, attr))
                return self.update(existing, commit=commit)

            self.session.add(obj)
            self._commit(commit)
            logger.info("Registro %s adicionado", obj)
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", self.model.__name__)
            raise

    def get_registers_for_plc(self, plc_id: int) -> List[Register]:
        """Provider utilizado pelo poller para carregar registradores activos."""

        registers = self.find_by(plc_id=plc_id, is_active=True)
        if registers:
            logger.debug("%d registradores activos encontrados para PLC %s", len(registers), plc_id)
        else:
            logger.warning("Nenhum registrador activo encontrado para PLC %s", plc_id)
        return registers


class OrganizationRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None) -> None:
        if Organization is None:
            raise RuntimeError("Modelo Organization não encontrado. Ajuste os imports.")
        super().__init__(Organization, session=session)

    def get_children(self, org_id: int) -> List[Organization]:
        org = self.get(org_id)
        if not org:
            return []
        return list(org.children)


RegRepo = RegisterRepo()
