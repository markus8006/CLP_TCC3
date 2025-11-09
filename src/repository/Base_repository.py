"""Infraestrutura simples de repositórios baseada em SQLAlchemy."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Type

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.app import db
from src.utils.logs import logger


class BaseRepo:
    """Implementa operações CRUD básicas com tratamento de erros consistente."""

    def __init__(self, model: Type[Any], session: Optional[Session] = None) -> None:
        self.model = model
        self.session = session or db.session

    # ------------------------------------------------------------------
    # Utilitários internos
    # ------------------------------------------------------------------
    def _commit(self, commit: bool) -> None:
        if commit:
            self.session.commit()
        else:
            self.session.flush()

    # ------------------------------------------------------------------
    # Operações de leitura
    # ------------------------------------------------------------------
    def get(self, id: int) -> Optional[Any]:
        try:
            return self.session.get(self.model, id)
        except SQLAlchemyError:
            logger.exception("Erro ao buscar %s id=%s", self.model.__name__, id)
            return None

    def list_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Any]:
        query = self.session.query(self.model).order_by(self.model.id)
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        try:
            return query.all()
        except SQLAlchemyError:
            logger.exception("Erro ao listar %s", self.model.__name__)
            return []

    def find_by(self, **filters: Any) -> List[Any]:
        try:
            return self.session.query(self.model).filter_by(**filters).all()
        except SQLAlchemyError:
            logger.exception("Erro em find_by %s filtros=%s", self.model.__name__, filters)
            return []

    def first_by(self, **filters: Any) -> Optional[Any]:
        try:
            return self.session.query(self.model).filter_by(**filters).first()
        except SQLAlchemyError:
            logger.exception("Erro em first_by %s filtros=%s", self.model.__name__, filters)
            return None

    def exists(self, **filters: Any) -> bool:
        try:
            return self.session.query(self.model).filter_by(**filters).first() is not None
        except SQLAlchemyError:
            logger.exception(
                "Erro ao verificar existência de %s com filtros=%s",
                self.model.__name__,
                filters,
            )
            return False

    # ------------------------------------------------------------------
    # Operações de escrita
    # ------------------------------------------------------------------
    def add(self, obj: Any, commit: bool = True) -> Any:
        try:
            self.session.add(obj)
            self._commit(commit)
            return obj
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar %s", self.model.__name__)
            raise

    def add_all(self, items: Iterable[Any], commit: bool = True) -> None:
        try:
            self.session.add_all(items)
            self._commit(commit)
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao adicionar múltiplos %s", self.model.__name__)
            raise

    def update(self, obj: Any, commit: bool = True) -> Any:
        try:
            merged = self.session.merge(obj)
            self._commit(commit)
            return merged
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao actualizar %s", self.model.__name__)
            raise

    def delete(self, obj: Any, commit: bool = True) -> bool:
        try:
            self.session.delete(obj)
            self._commit(commit)
            return True
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao apagar %s", self.model.__name__)
            raise

    def delete_by_id(self, id: int, commit: bool = True) -> bool:
        obj = self.get(id)
        if not obj:
            return False
        return self.delete(obj, commit=commit)
