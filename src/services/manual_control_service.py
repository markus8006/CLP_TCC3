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
    datalog: Optional[DataLog] = None


ALLOWED_COMMAND_TYPES: dict[str, dict[str, bool]] = {
    "setpoint": {"requires_numeric": True},
    "open": {"requires_numeric": False},
    "close": {"requires_numeric": False},
    "reset": {"requires_numeric": False},
}


def _normalise_note(note: Optional[str]) -> str:
    return (note or "").strip()


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

    def _validate_command(
        self,
        *,
        register: Register,
        command_type: str,
        value: Optional[float],
        note: Optional[str],
    ) -> None:
        command_type = (command_type or "").strip().lower()
        if command_type not in ALLOWED_COMMAND_TYPES:
            allowed = ", ".join(sorted(ALLOWED_COMMAND_TYPES))
            raise ValueError(f"Tipo de comando inválido. Utilize um dos seguintes: {allowed}.")

        requires_numeric = ALLOWED_COMMAND_TYPES[command_type]["requires_numeric"]
        if requires_numeric and value is None:
            raise ValueError("Comandos de setpoint exigem um valor numérico.")
        if not requires_numeric and value is not None:
            raise ValueError("Este tipo de comando não deve incluir valor numérico.")

        if value is not None:
            if register.min_value is not None and value < register.min_value:
                raise ValueError(
                    f"Valor {value} abaixo do mínimo permitido ({register.min_value})."
                )
            if register.max_value is not None and value > register.max_value:
                raise ValueError(
                    f"Valor {value} acima do máximo permitido ({register.max_value})."
                )

        cleaned_note = _normalise_note(note)
        if len(cleaned_note) < 5:
            raise ValueError("Inclua uma observação operacional com pelo menos 5 caracteres.")

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
        """Validate and enqueue a manual command for further approval/dispatch."""

        register = self._resolve_register(register_id)
        self._validate_command(
            register=register,
            command_type=command_type,
            value=value,
            note=note,
        )

        timestamp = datetime.now(timezone.utc)
        command = ManualCommand(
            plc_id=register.plc_id,
            register_id=register.id,
            command_type=command_type.strip().lower(),
            value_numeric=value,
            value_text=value_text,
            executed_by=executed_by,
            note=_normalise_note(note),
            status="pending",
            created_at=timestamp,
        )

        self.session.add(command)
        self.session.commit()

        return ManualCommandResult(command=command, datalog=None)

    def approve_command(
        self,
        command_id: int,
        *,
        approved_by: str,
        reviewer_note: Optional[str] = None,
    ) -> ManualCommand:
        command = (
            self.session.query(ManualCommand)
            .options(joinedload(ManualCommand.register).joinedload(Register.plc))
            .filter(ManualCommand.id == command_id)
            .first()
        )
        if not command:
            raise ValueError("Comando manual não encontrado.")
        if command.status != "pending":
            raise ValueError("Somente comandos pendentes podem ser aprovados.")

        command.status = "approved"
        command.approved_by = approved_by
        command.approved_at = datetime.now(timezone.utc)
        if reviewer_note:
            command.reviewer_note = reviewer_note.strip()

        self.session.add(command)
        self.session.commit()
        return command

    def reject_command(
        self,
        command_id: int,
        *,
        rejected_by: str,
        reason: str,
    ) -> ManualCommand:
        command = (
            self.session.query(ManualCommand)
            .filter(ManualCommand.id == command_id)
            .first()
        )
        if not command:
            raise ValueError("Comando manual não encontrado.")
        if command.status not in {"pending", "approved"}:
            raise ValueError("Somente comandos pendentes ou aprovados podem ser rejeitados.")

        command.status = "rejected"
        command.reviewer_note = reason.strip()
        command.rejected_by = rejected_by
        command.rejected_at = datetime.now(timezone.utc)

        self.session.add(command)
        self.session.commit()
        return command

    def dispatch_command(
        self,
        command_id: int,
        *,
        dispatcher: str,
        execution_note: Optional[str] = None,
    ) -> ManualCommandResult:
        command = (
            self.session.query(ManualCommand)
            .options(joinedload(ManualCommand.register).joinedload(Register.plc))
            .filter(ManualCommand.id == command_id)
            .first()
        )
        if not command:
            raise ValueError("Comando manual não encontrado.")
        if command.status != "approved":
            raise ValueError("Apenas comandos aprovados podem ser despachados.")

        register = command.register or self._resolve_register(command.register_id)

        timestamp = datetime.now(timezone.utc)
        datalog = DataLog(
            plc_id=command.plc_id,
            register_id=command.register_id,
            timestamp=timestamp,
            raw_value=(
                command.value_text
                if command.value_text is not None
                else (
                    str(command.value_numeric)
                    if command.value_numeric is not None
                    else command.command_type
                )
            ),
            value_float=command.value_numeric,
            value_int=(
                int(command.value_numeric)
                if command.value_numeric is not None
                else None
            ),
            unit=register.unit,
            quality="MANUAL",
            is_alarm=False,
        )

        register.last_value = datalog.raw_value
        register.last_read = timestamp

        command.status = "executed"
        command.dispatched_by = dispatcher
        command.dispatched_at = timestamp
        command.execution_note = _normalise_note(execution_note)
        command.datalog = datalog

        self.session.add_all([datalog, register, command])
        self.session.commit()
        return ManualCommandResult(command=command, datalog=datalog)

    def recent_commands(self, limit: int = 20) -> list[ManualCommand]:
        return (
            self.session.query(ManualCommand)
            .order_by(ManualCommand.created_at.desc())
            .limit(limit)
            .all()
        )

    def pending_commands(self) -> list[ManualCommand]:
        return (
            self.session.query(ManualCommand)
            .filter(ManualCommand.status == "pending")
            .order_by(ManualCommand.created_at.asc())
            .all()
        )


__all__ = ["ManualControlService", "ManualCommandResult"]
