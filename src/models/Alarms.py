# models/alarm.py
from src.app import db
from datetime import datetime, timezone

class AlarmDefinition(db.Model):
    __tablename__ = 'alarm_definition'
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    condition_type = db.Column(db.String(20), nullable=False)
    setpoint = db.Column(db.Float)
    deadband = db.Column(db.Float, default=0.0)

    priority = db.Column(db.String(20), default='MEDIUM')
    is_active = db.Column(db.Boolean, default=True)
    auto_acknowledge = db.Column(db.Boolean, default=False)

    email_enabled = db.Column(db.Boolean, default=False)
    email_recipients = db.Column(db.Text)

class Alarm(db.Model):
    __tablename__ = 'alarm'
    id = db.Column(db.Integer, primary_key=True)
    alarm_definition_id = db.Column(db.Integer, db.ForeignKey('alarm_definition.id'), nullable=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=True)

    state = db.Column(db.String(20), nullable=False)  # ACTIVE, ACKNOWLEDGED, CLEARED
    priority = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)

    triggered_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(100))
    cleared_at = db.Column(db.DateTime)

    trigger_value = db.Column(db.Float)
    current_value = db.Column(db.Float)
