from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import current_app, has_app_context

from src.app.extensions import db
from src.models.Data import DataLog
from src.repository.Data_repository import DataLogRepo
from src.repository.PLC_repository import PLCRepo
from src.repository.Registers_repository import RegisterRepo
from src.services.Alarms_service import AlarmService


class PollerIngestError(Exception):
    """Base exception for poller ingestion failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.context = context or {}


class PollerIngestProcessingError(PollerIngestError):
    """Raised when an unexpected failure happens during ingestion."""

    def __init__(
        self,
        message: str = "Erro ao processar dados",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, status_code=500, context=context)


def parse_timestamp(raw_ts: Any) -> Optional[datetime]:
    """Normalises timestamps accepted by the ingestion pipeline."""

    if raw_ts is None:
        return None
    if isinstance(raw_ts, datetime):
        return raw_ts
    if isinstance(raw_ts, (int, float)):
        return datetime.fromtimestamp(raw_ts, tz=timezone.utc)
    if isinstance(raw_ts, str):
        normalized = raw_ts.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"timestamp inválido: {raw_ts}") from exc
    raise ValueError(f"timestamp inválido: {raw_ts}")


def _log_exception(logger, message: str, *args: Any) -> None:
    if logger is None:
        if has_app_context():
            current_app.logger.exception(message, *args)
        return
    try:
        logger.exception(message, *args)
    except Exception:  # pragma: no cover - logger misbehaving
        pass


def process_poller_payload(
    payload: Dict[str, Any], *, session=None, logger=None
) -> Dict[str, Any]:
    """Persists a polling payload produced by the Go runtime.

    Parameters
    ----------
    payload:
        JSON-compatible dictionary produced by the Go polling runtime.
    session:
        SQLAlchemy session override. Defaults to :data:`db.session`.
    logger:
        Logger used for diagnostic messages. Falls back to ``current_app.logger`` when
        executed inside an application context.
    """

    if not isinstance(payload, dict):
        raise PollerIngestError("JSON inválido")

    session = session or db.session

    try:
        plc_id = int(payload.get("plc_id"))
        register_id = int(payload.get("register_id"))
    except (TypeError, ValueError) as exc:
        raise PollerIngestError("plc_id e register_id são obrigatórios") from exc

    status = (payload.get("status") or "online").strip().lower()

    try:
        timestamp = parse_timestamp(payload.get("timestamp")) or datetime.now(
            timezone.utc
        )
    except ValueError as exc:
        raise PollerIngestError(str(exc)) from exc

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    raw_value = payload.get("raw_value")
    value = payload.get("value")
    if raw_value is None:
        raw_value = value

    value_float = payload.get("value_float")
    if value_float is None and value is not None:
        try:
            value_float = float(value)
        except (TypeError, ValueError):
            value_float = None

    value_int = payload.get("value_int")
    if value_int is None and isinstance(value, int):
        value_int = value

    quality = payload.get("quality")
    unit = payload.get("unit")
    tags = payload.get("tags")
    error_message = payload.get("error")

    plc_repo = PLCRepo(session=session)
    register_repo = RegisterRepo(session=session)
    data_repo = DataLogRepo(session=session)
    alarm_service = AlarmService(session=session)

    plc = plc_repo.get(plc_id)
    if not plc:
        raise PollerIngestError(f"PLC {plc_id} não encontrado", status_code=404)

    register = register_repo.get(register_id)
    if not register or register.plc_id != plc.id:
        raise PollerIngestError(
            f"Registrador {register_id} não encontrado", status_code=404
        )

    try:
        is_alarm = alarm_service.check_and_handle(plc_id, register_id, value_float)
    except Exception as exc:  # pragma: no cover - defensive logging
        _log_exception(
            logger, "Erro ao avaliar alarmes para plc=%s reg=%s", plc_id, register_id
        )
        is_alarm = False

    data_entry = DataLog(
        plc_id=plc_id,
        register_id=register_id,
        timestamp=timestamp,
        raw_value=str(raw_value) if raw_value is not None else None,
        value_float=value_float,
        value_int=value_int,
        quality=quality,
        unit=unit,
        tags=tags,
        is_alarm=is_alarm,
    )

    try:
        data_repo.add(data_entry, commit=False)

        register.last_value = None if raw_value is None else str(raw_value)
        register.last_read = timestamp
        if status == "online":
            register.error_count = 0
            register.last_error = None
        else:
            register.error_count = (register.error_count or 0) + 1
            register.last_error = error_message or status

        is_online = status == "online"
        if plc.is_online != is_online:
            plc.is_online = is_online
            plc.status_changed_at = timestamp
        if is_online:
            plc.last_seen = timestamp
        elif status in {"offline", "error"}:
            plc.last_seen = None

        session.commit()
    except PollerIngestError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        context = {"plc_id": plc_id, "register_id": register_id}
        raise PollerIngestProcessingError(context=context) from exc

    return {"is_alarm": is_alarm, "data_log_id": getattr(data_entry, "id", None)}


def verify_internal_token(provided: Optional[str], expected: str) -> bool:
    if not provided or not expected:
        return False
    try:
        return hmac.compare_digest(provided, expected)
    except Exception:  # pragma: no cover - extremely defensive
        return provided == expected
