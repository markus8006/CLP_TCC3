"""Repositório especializado para entidades :class:`PLC`."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.PLCs import PLC
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger


class PLCRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None) -> None:
        if PLC is None:
            raise RuntimeError("Modelo PLC não encontrado. Ajuste os imports.")
        super().__init__(PLC, session=session)

    def get_by_ip(self, ip_address: str, vlan_id: Optional[int] = None) -> Optional[PLC]:
        query = self.session.query(self.model).filter(self.model.ip_address == ip_address)
        if vlan_id is not None:
            query = query.filter(self.model.vlan_id == vlan_id)
        try:
            return query.first()
        except SQLAlchemyError:
            logger.exception("Erro get_by_ip %s vlan=%s", ip_address, vlan_id)
            return None

    def delete_by_ip(self, ip_address: str, vlan_id: Optional[int] = None, commit: bool = True) -> bool:
        plc = self.get_by_ip(ip_address, vlan_id)
        if not plc:
            return False
        return self.delete(plc, commit=commit)

    def upsert_by_ip(self, plc_obj: PLC, commit: bool = True) -> PLC:
        """Insere ou atualiza um PLC com base em ``ip`` + ``vlan_id``."""

        existing = self.get_by_ip(plc_obj.ip_address, getattr(plc_obj, "vlan_id", None))
        if existing:
            for attr in [
                "name",
                "description",
                "protocol",
                "port",
                "unit_id",
                "rack_slot",
                "is_active",
            ]:
                if hasattr(plc_obj, attr):
                    setattr(existing, attr, getattr(plc_obj, attr))
            return self.update(existing, commit=commit)
        return self.add(plc_obj, commit=commit)

    def add(self, obj: Any, commit: bool = True) -> Any:
        """Garante unicidade básica por IP/VLAN antes de inserir."""

        try:
            existing = self.get_by_ip(obj.ip_address, getattr(obj, "vlan_id", None))
            if existing:
                logger.info("PLC %s já existe — atualizando dados básicos.", existing.id)
                for attr in [
                    "name",
                    "description",
                    "protocol",
                    "port",
                    "unit_id",
                    "rack_slot",
                    "mac_address",
                ]:
                    if hasattr(obj, attr):
                        setattr(existing, attr, getattr(obj, attr))
                return self.update(existing, commit=commit)

            self.session.add(obj)
            self._commit(commit)
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", self.model.__name__)
            raise

    def update_tags(self, plc: PLC, tags: Iterable[str], commit: bool = True) -> PLC:
        """Atualiza a lista de tags normalizada para um CLP."""

        try:
            plc.set_tags(tags)
            self._commit(commit)
            return plc
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao atualizar tags do PLC %s", plc.id if plc else "desconhecido")
            raise

    def set_active_state(
        self,
        plc: PLC,
        active: bool,
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        source: Optional[str] = None,
        commit: bool = True,
    ) -> PLC:
        """Atualiza o estado operativo do CLP com metadados de auditoria."""

        try:
            previous_state = plc.is_active
            if active:
                plc.mark_active(actor=actor, source=source)
            else:
                plc.mark_inactive(actor=actor, reason=reason, source=source)

            if previous_state != active:
                logger.info(
                    "Estado do CLP %s alterado de %s para %s por %s",
                    plc.id,
                    previous_state,
                    active,
                    actor or "sistema",
                )

            self._commit(commit)
            return plc
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception(
                "Erro ao atualizar estado do PLC %s", plc.id if plc else "desconhecido"
            )
            raise


Plcrepo = PLCRepo()
