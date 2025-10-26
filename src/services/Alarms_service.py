"""Alarm evaluation helpers with email notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.app import db
from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Users import User, UserRole
from src.repository.Alarms_repository import AlarmDefinitionRepo, AlarmRepo
from src.services.email_service import send_email
from src.utils.logs import logger


def evaluate_alarm(defn: AlarmDefinition, value: float, existing_alarm: Optional[Alarm]) -> Tuple[str, Dict[str, object]]:
    """Determine the action that should be taken for the given reading."""

    now = datetime.now(timezone.utc)
    if value is None:
        return "none", {}

    cond = defn.condition_type
    low = defn.threshold_low
    high = defn.threshold_high
    sp = defn.setpoint
    dband = defn.deadband or 0.0

    in_cond = False
    if cond == "above":
        if sp is None:
            return "none", {}
        in_cond = value > sp
        msg = f"Value {value} > setpoint {sp}"
    elif cond == "below":
        if sp is None:
            return "none", {}
        in_cond = value < sp
        msg = f"Value {value} < setpoint {sp}"
    elif cond == "outside_range":
        if low is None or high is None:
            return "none", {}
        in_cond = (value < low) or (value > high)
        msg = f"Value {value} outside [{low}, {high}]"
    elif cond == "inside_range":
        if low is None or high is None:
            return "none", {}
        in_cond = low <= value <= high
        msg = f"Value {value} inside [{low}, {high}]"
    else:
        return "none", {}

    if existing_alarm is None or existing_alarm.state != "ACTIVE":
        if in_cond:
            return "trigger", {
                "message": msg,
                "trigger_value": value,
                "triggered_at": now,
            }
        return "none", {}

    if existing_alarm.state == "ACTIVE":
        if cond == "above":
            safe = value <= (sp - dband)
            if safe:
                return "clear", {"cleared_at": now, "current_value": value}
        elif cond == "below":
            safe = value >= (sp + dband)
            if safe:
                return "clear", {"cleared_at": now, "current_value": value}
        elif cond == "outside_range":
            safe = (low + dband) <= value <= (high - dband)
            if safe:
                return "clear", {"cleared_at": now, "current_value": value}
        elif cond == "inside_range":
            safe = not (low <= value <= high)
            if safe:
                return "clear", {"cleared_at": now, "current_value": value}

    return "none", {}


class AlarmService:
    def __init__(self, session=None):
        self.def_repo = AlarmDefinitionRepo(session=session)
        self.alarm_repo = AlarmRepo(session=session)

    def _find_active_alarm_for_definition(self, defn: AlarmDefinition) -> Optional[Alarm]:
        return self.alarm_repo.first_by(alarm_definition_id=defn.id, state="ACTIVE")

    def _create_alarm(
        self,
        defn: AlarmDefinition,
        plc_id: int,
        register_id: int,
        trigger_value: float,
        current_value: float,
        message: str,
    ) -> Alarm:
        now = datetime.now(timezone.utc)
        alarm = Alarm(
            alarm_definition_id=defn.id,
            plc_id=plc_id,
            register_id=register_id,
            state="ACTIVE",
            priority=defn.priority or "MEDIUM",
            message=message,
            triggered_at=now,
            trigger_value=trigger_value,
            current_value=current_value,
        )
        self.alarm_repo.add(alarm)
        logger.info("Alarm triggered: %s (def=%s plc=%s reg=%s)", message, defn.id, plc_id, register_id)
        self._notify_trigger(defn, alarm)
        return alarm

    def _clear_alarm(self, defn: AlarmDefinition, alarm: Alarm, current_value: float) -> None:
        now = datetime.now(timezone.utc)
        alarm.state = "CLEARED"
        alarm.cleared_at = now
        alarm.current_value = current_value
        self.alarm_repo.update(alarm)
        logger.info("Alarm cleared: id=%s def=%s", alarm.id, alarm.alarm_definition_id)
        self._notify_clear(defn, alarm)

    def check_and_handle(self, plc_id: int, register_id: int, value: Optional[float]) -> bool:
        if value is None:
            return False

        triggered_any = False
        defs: List[AlarmDefinition] = self.def_repo.find_by(plc_id=plc_id, register_id=register_id, is_active=True)

        for defn in defs:
            try:
                existing_alarm = self._find_active_alarm_for_definition(defn)
                action, info = evaluate_alarm(defn, value, existing_alarm)

                if action == "trigger":
                    if existing_alarm is None or existing_alarm.state != "ACTIVE":
                        message = info.get("message") or f"Alarm {defn.name} triggered"
                        trigger_val = info.get("trigger_value", value)
                        self._create_alarm(defn, plc_id, register_id, trigger_val, value, message)
                        triggered_any = True
                    else:
                        existing_alarm.current_value = value
                        self.alarm_repo.update(existing_alarm)

                elif action == "clear":
                    if existing_alarm is not None and existing_alarm.state == "ACTIVE":
                        self._clear_alarm(defn, existing_alarm, info.get("current_value", value))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Erro avaliando alarme def=%s: %s", getattr(defn, "id", None), exc)
                continue

        return triggered_any

    # ------------------------------------------------------------------
    # Email helpers
    # ------------------------------------------------------------------
    def _notify_trigger(self, defn: AlarmDefinition, alarm: Alarm) -> None:
        if not getattr(defn, "email_enabled", False):
            return
        recipients = self._resolve_recipients(defn)
        if not recipients:
            logger.debug("Nenhum destinatário encontrado para email de alarme def=%s", defn.id)
            return

        subject = f"[ALARME {defn.priority or 'MEDIUM'}] {defn.name}"
        body = self._format_trigger_body(defn, alarm)
        send_email(subject, body, recipients)

    def _notify_clear(self, defn: AlarmDefinition, alarm: Alarm) -> None:
        if not getattr(defn, "email_enabled", False):
            return
        recipients = self._resolve_recipients(defn)
        if not recipients:
            return

        subject = f"[ALARME {defn.priority or 'MEDIUM'}] {defn.name} normalizado"
        body = self._format_clear_body(defn, alarm)
        send_email(subject, body, recipients)

    def _resolve_recipients(self, defn: AlarmDefinition) -> List[str]:
        min_role = getattr(defn, "email_min_role", UserRole.ALARM_DEFINITION)
        if isinstance(min_role, str):
            try:
                min_role = UserRole(min_role)
            except ValueError:
                min_role = UserRole.ALARM_DEFINITION

        recipients: List[str] = []
        try:
            users = db.session.query(User).filter_by(is_active=True).all()
        except Exception:
            logger.exception("Erro ao obter utilizadores para notificação de alarme")
            return recipients

        for user in users:
            try:
                if user.has_permission(min_role):
                    recipients.append(user.email)
            except Exception:
                logger.debug("Erro ao avaliar permissões do utilizador %s", getattr(user, "id", "unknown"))
        return recipients

    def _format_trigger_body(self, defn: AlarmDefinition, alarm: Alarm) -> str:
        plc_name = getattr(defn.plc, "name", None) if hasattr(defn, "plc") else None
        register_name = getattr(defn.register, "name", None) if hasattr(defn, "register") else None
        lines = [
            f"Alarme: {defn.name}",
            f"Prioridade: {defn.priority or 'MEDIUM'}",
            f"PLC: {plc_name or defn.plc_id}",
            f"Registrador: {register_name or defn.register_id}",
            f"Mensagem: {alarm.message}",
            f"Valor actual: {alarm.current_value}",
            f"Valor de disparo: {alarm.trigger_value}",
            f"Ocorrido em: {alarm.triggered_at.strftime('%Y-%m-%d %H:%M:%S %Z') if alarm.triggered_at else 'N/D'}",
        ]
        if defn.description:
            lines.extend(["", "Descrição:", defn.description])
        return "\n".join(str(line) for line in lines if line is not None)

    def _format_clear_body(self, defn: AlarmDefinition, alarm: Alarm) -> str:
        plc_name = getattr(defn.plc, "name", None) if hasattr(defn, "plc") else None
        register_name = getattr(defn.register, "name", None) if hasattr(defn, "register") else None
        lines = [
            f"O alarme {defn.name} foi normalizado.",
            f"Prioridade: {defn.priority or 'MEDIUM'}",
            f"PLC: {plc_name or defn.plc_id}",
            f"Registrador: {register_name or defn.register_id}",
            f"Valor actual: {alarm.current_value}",
            f"Limpado em: {alarm.cleared_at.strftime('%Y-%m-%d %H:%M:%S %Z') if alarm.cleared_at else 'N/D'}",
        ]
        return "\n".join(str(line) for line in lines if line is not None)


__all__ = ["AlarmService", "evaluate_alarm"]

