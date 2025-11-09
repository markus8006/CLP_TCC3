"""Repositório especializado para registros de dados históricos."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.Data import DataLog
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger


class DataLogRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None) -> None:
        if DataLog is None:
            raise RuntimeError("Modelo DataLog não encontrado. Ajuste os imports.")
        super().__init__(DataLog, session=session)

    def list_recent(self, plc_id: int, register_id: int, limit: int = 100) -> List[DataLog]:
        query = (
            self.session.query(self.model)
            .filter(
                self.model.plc_id == plc_id,
                self.model.register_id == register_id,
            )
            .order_by(self.model.timestamp.desc())
            .limit(limit)
        )
        try:
            return query.all()
        except SQLAlchemyError:
            logger.exception("Erro list_recent datalog plc=%s reg=%s", plc_id, register_id)
            return []

    def bulk_insert(
        self,
        records: Iterable[Dict[str, Any]],
        *,
        commit: bool = True,
        batch_size: int = 5000,
    ) -> int:
        """Insere diversos registros na tabela ``data_log``."""

        records_list = list(records)
        if not records_list:
            return 0

        inserted = 0
        try:
            for start in range(0, len(records_list), batch_size):
                batch = records_list[start : start + batch_size]
                self.session.bulk_insert_mappings(self.model, batch)
                inserted += len(batch)

            if commit:
                self.session.commit()
            else:
                self.session.flush()
            return inserted
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro bulk_insert DataLog")
            raise

    def _cleanup_old_records(self, records: Iterable[Dict[str, Any]]) -> None:
        """Mantém apenas os 30 registros mais recentes por CLP/registrador."""

        keys: Tuple[Tuple[int, int], ...] = tuple(
            { (rec["plc_id"], rec["register_id"]) for rec in records }
        )
        if not keys:
            return

        cleanup_sql = """
        WITH ranked_records AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY plc_id, register_id
                       ORDER BY timestamp DESC
                   ) AS rn
            FROM data_log
            WHERE (plc_id, register_id) IN :keys
        )
        DELETE FROM data_log
        WHERE id IN (
            SELECT id FROM ranked_records WHERE rn > 30
        )
        """

        try:
            self.session.execute(text(cleanup_sql), {"keys": keys})
        except SQLAlchemyError:
            # Em ambientes sem suporte a CTEs avançadas (ex.: SQLite em memória)
            # preferimos apenas registar o erro e seguir sem interromper a inserção.
            logger.warning("Não foi possível limpar registros antigos de data_log", exc_info=True)

    # Compatibilidade com código antigo/tests
    def _cleanup_old_records_optimized(self, records: Iterable[Dict[str, Any]]) -> None:
        self._cleanup_old_records(records)


DataRepo = DataLogRepo()
