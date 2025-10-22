# models/alarm.py
from src.app import db
from datetime import datetime, timezone

# models/alarm.py (sugestão de atualização)
from src.app import db
from datetime import datetime, timezone

class AlarmDefinition(db.Model):
    __tablename__ = 'alarm_definition'
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # Tipo de condição: 'above', 'below', 'outside_range', 'inside_range', 'change', ...
    condition_type = db.Column(db.String(30), nullable=False, default='above')

    # Suporta setpoint único (setpoint) e/ou limites (threshold_low/threshold_high)
    setpoint = db.Column(db.Float, nullable=True)
    threshold_low = db.Column(db.Float, nullable=True)
    threshold_high = db.Column(db.Float, nullable=True)

    # deadband/hysteresis em unidades da variável (ex.: 0.5)
    deadband = db.Column(db.Float, default=0.0)

    priority = db.Column(db.String(20), default='MEDIUM')
    is_active = db.Column(db.Boolean, default=True)
    auto_acknowledge = db.Column(db.Boolean, default=False)

    email_enabled = db.Column(db.Boolean, default=False)
    email_recipients = db.Column(db.Text)

    # opcional: severidade numérica para ordenação/alertas
    severity = db.Column(db.Integer, default=3)


class Alarm(db.Model):
    __tablename__ = 'alarm'
    id = db.Column(db.Integer, primary_key=True)
    alarm_definition_id = db.Column(db.Integer, db.ForeignKey('alarm_definition.id'), nullable=True, index=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False, index=True)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=True, index=True)

    state = db.Column(db.String(20), nullable=False)  # ACTIVE, ACKNOWLEDGED, CLEARED
    priority = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)

    triggered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(100))
    cleared_at = db.Column(db.DateTime)

    trigger_value = db.Column(db.Float)
    current_value = db.Column(db.Float)

    last_updated_at = db.Column(db.DateTime, nullable=True)