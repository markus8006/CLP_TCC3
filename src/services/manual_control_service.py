"""Service responsible for manual overrides triggered from the HMI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import joinedload

from src.app.extensions import db
from src.models.Data import DataLog
from src.models.ManualControl import ManualCommand
from src.models.Registers import Register


@dataclass
class ManualCommandResult:
    """Return value for manual command executions."""

    command: ManualCommand
    datalog: DataLog


class ManualControlService:
    """Encapsulates the logic to persist manual commands and their side effects."""

    def __init__(self, session=None):
        self.session = session or db.session

    def _resolve_register(self, register_id: int) -> Register:
        register = (
            self.session.query(Register)
            .options(joinedload(Register.plc))
            .filter(Register.id == register_id)
            .first()
        )
        if not register:
            raise ValueError("Registrador não encontrado para controle manual.")
        if not register.is_active:
            raise ValueError("Registrador inativo não permite intervenção manual.")
        if not register.plc or not register.plc.is_active:
            raise ValueError("O CLP associado está inativo ou indisponível.")
        return register

    def execute_command(
        self,
        *,
        register_id: int,
        command_type: str,
        value: Optional[float] = None,
        value_text: Optional[str] = None,
        executed_by: str,
        note: Optional[str] = None,
    ) -> ManualCommandResult:
        """Persist a manual command and record the manual value in the historian."""

        register = self._resolve_register(register_id)
        timestamp = datetime.now(timezone.utc)

        datalog = DataLog(
            plc_id=register.plc_id,
            register_id=register.id,
            timestamp=timestamp,
            raw_value=value_text if value_text is not None else str(value),
            value_float=value,
            value_int=int(value) if value is not None else None,
            unit=register.unit,
            quality="MANUAL",
            is_alarm=False,
        )
        register.last_value = datalog.raw_value
        register.last_read = timestamp

        command = ManualCommand(
            plc_id=register.plc_id,
            register_id=register.id,
            command_type=command_type,
            value_numeric=value,
            value_text=value_text,
            executed_by=executed_by,
            note=note,
            status="executed",
            created_at=timestamp,
        )

        self.session.add_all([datalog, command, register])
        self.session.commit()

        return ManualCommandResult(command=command, datalog=datalog)

    def recent_commands(self, limit: int = 20) -> list[ManualCommand]:
        return (
            self.session.query(ManualCommand)
            .order_by(ManualCommand.created_at.desc())
            .limit(limit)
            .all()
        )


__all__ = ["ManualControlService", "ManualCommandResult"]
