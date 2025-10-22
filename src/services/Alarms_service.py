# src/services/alarm_service.py
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from src.repository.Alarms_repository import AlarmDefinitionRepo, AlarmRepo
from src.models.Alarms import Alarm, AlarmDefinition
from src.utils.logs import logger





 # ======HELPER=========
def evaluate_alarm(defn, value: float, existing_alarm: Optional[Alarm]) -> Tuple[str, dict]:
    """
    Retorna (action, info) onde action é: 'trigger', 'clear', 'none'.
    info é dict com dados úteis (message, trigger_value, now).
    defn: AlarmDefinition ORM
    existing_alarm: Alarm ORM ativo (ou None)
    """
    now = datetime.now(timezone.utc)
    if value is None:
        return 'none', {}

    cond = defn.condition_type  # ex: 'above', 'below', 'outside_range'
    low = defn.threshold_low
    high = defn.threshold_high
    sp = defn.setpoint
    dband = defn.deadband or 0.0

    # Helper: is_in_alarm_condition (ignoring deadband)
    in_cond = False
    if cond == 'above':
        if sp is None:
            return 'none', {}
        in_cond = value > sp
        msg = f"Value {value} > setpoint {sp}"
    elif cond == 'below':
        if sp is None:
            return 'none', {}
        in_cond = value < sp
        msg = f"Value {value} < setpoint {sp}"
    elif cond == 'outside_range':
        if low is None or high is None:
            return 'none', {}
        in_cond = (value < low) or (value > high)
        msg = f"Value {value} outside [{low}, {high}]"
    elif cond == 'inside_range':
        if low is None or high is None:
            return 'none', {}
        in_cond = (low <= value <= high)
        msg = f"Value {value} inside [{low}, {high}]"
    else:
        # outras condições possíveis: 'change', 'rate', ...
        return 'none', {}

    # Se não há alarme ativo e condição true => TRIGGER
    if existing_alarm is None or existing_alarm.state != 'ACTIVE':
        if in_cond:
            return 'trigger', {
                'message': msg,
                'trigger_value': value,
                'triggered_at': now
            }
        return 'none', {}

    # Se já há um alarme ativo: só CLEAR se o valor voltou para dentro da zona segura
    # aplicando deadband: para 'above' com setpoint=sp:
    #  - alarme ativado quando value > sp
    #  - só limpar quando value <= sp - deadband
    # para 'below':
    #  - ativado quando value < sp
    #  - limpar quando value >= sp + deadband
    if existing_alarm.state == 'ACTIVE':
        if cond == 'above':
            safe = value <= (sp - dband)
            if safe:
                return 'clear', {'cleared_at': now, 'current_value': value}
        elif cond == 'below':
            safe = value >= (sp + dband)
            if safe:
                return 'clear', {'cleared_at': now, 'current_value': value}
        elif cond == 'outside_range':
            # clear when value enters [low+db, high-db]
            safe = (low + dband) <= value <= (high - dband)
            if safe:
                return 'clear', {'cleared_at': now, 'current_value': value}
        elif cond == 'inside_range':
            # clear when value leaves the inside_range? depends on semantics
            safe = not ((low <= value <= high))
            if safe:
                return 'clear', {'cleared_at': now, 'current_value': value}

    return 'none', {}






class AlarmService:
    def __init__(self, session=None):
        # repos usam db.session por padrão, mas aceitam session opcional
        self.def_repo = AlarmDefinitionRepo(session=session)
        self.alarm_repo = AlarmRepo(session=session)

    def _find_active_alarm_for_definition(self, defn: AlarmDefinition) -> Optional[Alarm]:
        # procura um Alarm ativo para esta definição (um por definição)
        return self.alarm_repo.first_by(alarm_definition_id=defn.id, state='ACTIVE')

    def _create_alarm(self, defn: AlarmDefinition, plc_id: int, register_id: int, trigger_value: float, current_value: float, message: str) -> Alarm:
        now = datetime.now(timezone.utc)
        alarm = Alarm(
            alarm_definition_id=defn.id,
            plc_id=plc_id,
            register_id=register_id,
            state='ACTIVE',
            priority=defn.priority or 'MEDIUM',
            message=message,
            triggered_at=now,
            trigger_value=trigger_value,
            current_value=current_value
        )
        # salva e retorna
        self.alarm_repo.add(alarm)
        logger.info("Alarm triggered: %s (def=%s plc=%s reg=%s)", message, defn.id, plc_id, register_id)
        # TODO: disparar notificações/alerts aqui (email, ws) se defn.email_enabled
        return alarm

    def _clear_alarm(self, alarm: Alarm, current_value: float):
        now = datetime.now(timezone.utc)
        alarm.state = 'CLEARED'
        alarm.cleared_at = now
        alarm.current_value = current_value
        self.alarm_repo.update(alarm)
        logger.info("Alarm cleared: id=%s def=%s", alarm.id, alarm.alarm_definition_id)
        # TODO: notificar limpeza se necessário

    def check_and_handle(self, plc_id: int, register_id: int, value: Optional[float]) -> bool:
        """
        Checa todas as AlarmDefinitions ativas para (plc_id, register_id) e cria/limpa alarms conforme necessário.
        Retorna True se qualquer alarme foi disparado nesta leitura.
        """
        if value is None:
            return False

        triggered_any = False
        # Buscar definições ativas para este plc/register.
        # Você pode querer também buscar definições com register_id is NULL para alarms por plc genéricos.
        defs: List[AlarmDefinition] = self.def_repo.find_by(plc_id=plc_id, register_id=register_id, is_active=True)

        for defn in defs:
            try:
                existing_alarm = self._find_active_alarm_for_definition(defn)
                action, info = evaluate_alarm(defn, value, existing_alarm)

                if action == 'trigger':
                    # se já existe alarme ativo para essa definição não criar duplicado (mas sua evaluate deveria ter evitado isso)
                    if existing_alarm is None or existing_alarm.state != 'ACTIVE':
                        message = info.get('message') or f"Alarm {defn.name} triggered"
                        trigger_val = info.get('trigger_value', value)
                        self._create_alarm(defn, plc_id, register_id, trigger_val, value, message)
                        triggered_any = True
                    else:
                        # já ativo -> podemos atualizar current_value e triggered_at se quiser
                        existing_alarm.current_value = value
                        self.alarm_repo.update(existing_alarm)

                elif action == 'clear':
                    if existing_alarm is not None and existing_alarm.state == 'ACTIVE':
                        self._clear_alarm(existing_alarm, info.get('current_value', value))
                # action == 'none' -> nada a fazer
            except Exception as e:
                logger.exception("Erro avaliando alarme def=%s: %s", getattr(defn, 'id', None), e)
                continue

        return triggered_any
