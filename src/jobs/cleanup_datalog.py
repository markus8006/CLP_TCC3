"""Job de limpeza global da tabela ``data_log``.

Este script executa a mesma lógica anteriormente embutida no ``DataLogRepo``
para remoção de históricos antigos, porém agora dedicada a uma tarefa
assíncrona agendada (ex.: via cron ou scheduler externo).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text

from src.app import create_app, db
from src.app.settings import load_settings
from src.utils.logs import logger


CLEANUP_SQL = """
WITH ranked_records AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY plc_id, register_id
               ORDER BY timestamp DESC
           ) AS rn
    FROM data_log
)
DELETE FROM data_log
WHERE id IN (
    SELECT id FROM ranked_records WHERE rn > :max_records
)
"""


def cleanup_data_log(*, max_records_per_register: int = 30) -> int:
    """Remove registros antigos da ``data_log`` mantendo o limite desejado."""

    settings = load_settings()
    if settings.demo.enabled and settings.demo.read_only:
        logger.info("Modo demo em leitura; limpeza global de DataLog ignorada")
        return 0

    try:
        app = create_app(settings.environment)
    except TypeError:
        app = create_app()
    with app.app_context():
        start = datetime.utcnow()
        logger.info(
            "Iniciando limpeza global de data_log (máx %s registros por registrador)",
            max_records_per_register,
        )
        try:
            result = db.session.execute(
                text(CLEANUP_SQL), {"max_records": max_records_per_register}
            )
            deleted = result.rowcount or 0
            db.session.commit()
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info(
                "Limpeza concluída: %s registros removidos em %.2fs",
                deleted,
                elapsed,
            )
            return deleted
        except Exception:
            db.session.rollback()
            logger.exception("Falha ao executar limpeza global da tabela data_log")
            raise


def main(args: Optional[list[str]] = None) -> int:
    """Ponto de entrada para execução via ``python -m`` ou console."""

    deleted = cleanup_data_log()
    return 0 if deleted >= 0 else 1


if __name__ == "__main__":  # pragma: no cover - ponto de entrada de script
    raise SystemExit(main())
