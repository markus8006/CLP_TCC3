"""Serviços administrativos para definições de alarme."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.app import db
from src.models.Alarms import AlarmDefinition
from src.models.Users import UserRole
from src.repository.Alarms_repository import AlarmDefinitionRepo


def _get_repo(session: Optional[Session]) -> AlarmDefinitionRepo:
    return AlarmDefinitionRepo(session=session or db.session)


def create_alarm_definition(
    data: Dict[str, Any],
    *,
    session: Optional[Session] = None,
) -> AlarmDefinition:
    """Constrói e persiste uma definição de alarme a partir dos dados do formulário."""

    repo = _get_repo(session)
    register_id = data.get("register_id")
    payload: Dict[str, Any] = {
        "plc_id": data.get("plc_id"),
        "register_id": register_id if register_id not in (None, 0) else None,
        "name": data.get("name"),
        "description": data.get("description"),
        "condition_type": data.get("condition_type"),
        "setpoint": data.get("setpoint"),
        "threshold_low": data.get("threshold_low"),
        "threshold_high": data.get("threshold_high"),
        "deadband": data.get("deadband") if data.get("deadband") is not None else 0.0,
        "priority": data.get("priority"),
        "severity": data.get("severity") if data.get("severity") is not None else 3,
        "is_active": data.get("is_active"),
        "auto_acknowledge": data.get("auto_acknowledge"),
        "email_enabled": data.get("email_enabled"),
        "email_min_role": UserRole(data.get("email_min_role")),
    }

    definition = AlarmDefinition(**payload)
    return repo.add(definition, commit=True)


def delete_alarm_definition(
    definition: AlarmDefinition,
    *,
    session: Optional[Session] = None,
) -> None:
    repo = _get_repo(session)
    repo.session.delete(repo.session.merge(definition))
    repo.session.commit()
