"""Alarm evaluation helpers with email notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

from src.app import db
from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Users import User, UserRole
from src.repository.Alarms_repository import AlarmDefinitionRepo, AlarmRepo
from src.services.email_service import send_email
from src.services.mqtt_service import get_mqtt_publisher
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
        self.mqtt_publisher = get_mqtt_publisher()

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
        try:
            self.mqtt_publisher.publish_alarm_event(defn, alarm, state="ACTIVE")
        except Exception:
            logger.exception("Erro ao publicar alarme %s no MQTT", getattr(defn, "id", None))
        return alarm

    def _clear_alarm(self, defn: AlarmDefinition, alarm: Alarm, current_value: float) -> None:
        now = datetime.now(timezone.utc)
        alarm.state = "CLEARED"
        alarm.cleared_at = now
        alarm.current_value = current_value
        self.alarm_repo.update(alarm)
        logger.info("Alarm cleared: id=%s def=%s", alarm.id, alarm.alarm_definition_id)
        self._notify_clear(defn, alarm)
        try:
            self.mqtt_publisher.publish_alarm_event(defn, alarm, state="CLEARED")
        except Exception:
            logger.exception("Erro ao publicar normalização do alarme %s no MQTT", getattr(defn, "id", None))

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
                        try:
                            self.mqtt_publisher.publish_alarm_event(defn, existing_alarm, state="ACTIVE")
                        except Exception:
                            logger.exception(
                                "Erro ao publicar atualização do alarme ativo %s no MQTT",
                                getattr(defn, "id", None),
                            )

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
        text_body, html_body = self._format_trigger_body(defn, alarm)
        try:
            send_email(subject, text_body, recipients, html_body=html_body)
        except TypeError:
            send_email(subject, text_body, recipients)

    def _notify_clear(self, defn: AlarmDefinition, alarm: Alarm) -> None:
        if not getattr(defn, "email_enabled", False):
            return
        recipients = self._resolve_recipients(defn)
        if not recipients:
            return

        subject = f"[ALARME {defn.priority or 'MEDIUM'}] {defn.name} normalizado"
        text_body, html_body = self._format_clear_body(defn, alarm)
        try:
            send_email(subject, text_body, recipients, html_body=html_body)
        except TypeError:
            send_email(subject, text_body, recipients)

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

    def _format_trigger_body(self, defn: AlarmDefinition, alarm: Alarm) -> Tuple[str, str]:
        plc_name = getattr(defn.plc, "name", None) if hasattr(defn, "plc") else None
        register_name = getattr(defn.register, "name", None) if hasattr(defn, "register") else None
        occurred_at = (
            alarm.triggered_at.strftime("%Y-%m-%d %H:%M:%S %Z")
            if alarm.triggered_at
            else "N/D"
        )
        text_lines = [
            f"Alarme: {defn.name}",
            f"Prioridade: {defn.priority or 'MEDIUM'}",
            f"PLC: {plc_name or defn.plc_id}",
            f"Registrador: {register_name or defn.register_id}",
            f"Mensagem: {alarm.message}",
            f"Valor atual: {alarm.current_value}",
            f"Valor de disparo: {alarm.trigger_value}",
            f"Ocorrido em: {occurred_at}",
        ]
        if defn.description:
            text_lines.extend(["", "Descrição:", defn.description])

        html_body = self._build_email_html(
            title="Alerta de Alarme",
            subtitle=f"{escape(defn.name or 'Alarme')} · Prioridade {escape(defn.priority or 'MEDIUM')}",
            rows=[
                ("PLC", plc_name or defn.plc_id),
                ("Registrador", register_name or defn.register_id),
                ("Mensagem", alarm.message),
                ("Valor atual", alarm.current_value),
                ("Valor de disparo", alarm.trigger_value),
                ("Ocorrido em", occurred_at),
            ],
            description=defn.description,
        )

        return "\n".join(str(line) for line in text_lines if line is not None), html_body

    def _format_clear_body(self, defn: AlarmDefinition, alarm: Alarm) -> Tuple[str, str]:
        plc_name = getattr(defn.plc, "name", None) if hasattr(defn, "plc") else None
        register_name = getattr(defn.register, "name", None) if hasattr(defn, "register") else None
        cleared_at = (
            alarm.cleared_at.strftime("%Y-%m-%d %H:%M:%S %Z") if alarm.cleared_at else "N/D"
        )
        text_lines = [
            f"O alarme {defn.name} foi normalizado.",
            f"Prioridade: {defn.priority or 'MEDIUM'}",
            f"PLC: {plc_name or defn.plc_id}",
            f"Registrador: {register_name or defn.register_id}",
            f"Valor atual: {alarm.current_value}",
            f"Limpado em: {cleared_at}",
        ]

        html_body = self._build_email_html(
            title="Alarme Normalizado",
            subtitle=f"{escape(defn.name or 'Alarme')} · Prioridade {escape(defn.priority or 'MEDIUM')}",
            rows=[
                ("PLC", plc_name or defn.plc_id),
                ("Registrador", register_name or defn.register_id),
                ("Valor atual", alarm.current_value),
                ("Normalizado em", cleared_at),
            ],
            description="O alarme foi normalizado e encontra-se estável.",
        )

        return "\n".join(str(line) for line in text_lines if line is not None), html_body

    def _build_email_html(
        self,
        *,
        title: str,
        subtitle: str,
        rows: Sequence[Tuple[str, object]],
        description: Optional[str] = None,
    ) -> str:
        description_html = ""
        if description:
            escaped_description = escape(str(description)).replace("\n", "<br />")
            description_html = (
                "<div class=\"card__section\">"
                "<h3>Descrição</h3>"
                f"<p>{escaped_description}</p>"
                "</div>"
            )

        rows_html = "".join(
            """
            <tr>
              <th>{label}</th>
              <td>{value}</td>
            </tr>
            """.format(
                label=escape(str(label)),
                value=escape(str(value))
            )
            for label, value in rows
            if value is not None
        )

        return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <style>
      body {{
        margin: 0;
        background: #f5f7fb;
        font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
        color: #1f2937;
        padding: 32px 0;
      }}
      .card {{
        max-width: 560px;
        margin: 0 auto;
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 20px 45px rgba(15, 23, 42, 0.12);
        overflow: hidden;
      }}
      .card__header {{
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        color: #ffffff;
        padding: 28px 32px;
      }}
      .card__header h1 {{
        margin: 0;
        font-size: 22px;
        font-weight: 600;
      }}
      .card__header p {{
        margin: 6px 0 0;
        font-size: 15px;
        opacity: 0.85;
      }}
      .card__section {{
        padding: 24px 32px;
        border-bottom: 1px solid #eef2ff;
      }}
      .card__section:last-child {{
        border-bottom: none;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th {{
        text-align: left;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6b7280;
        padding: 8px 0;
        width: 35%;
      }}
      td {{
        padding: 8px 0;
        font-size: 15px;
        color: #111827;
      }}
      .card__footer {{
        padding: 20px 32px 28px;
        font-size: 13px;
        color: #6b7280;
        background: #f9fafb;
      }}
    </style>
  </head>
  <body>
    <div class=\"card\">
      <div class=\"card__header\">
        <h1>{escape(title)}</h1>
        <p>{escape(subtitle)}</p>
      </div>
      <div class=\"card__section\">
        <table>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
      {description_html}
      <div class=\"card__footer\">Esta é uma mensagem automática do sistema de monitorização de alarmes.</div>
    </div>
  </body>
</html>"""


__all__ = ["AlarmService", "evaluate_alarm"]

