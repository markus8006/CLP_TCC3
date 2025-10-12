from src.app import db
from datetime import datetime


class AlarmDefinition(db.Model):
    """Definições de alarmes"""
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'))
    
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Condições
    condition_type = db.Column(db.String(20), nullable=False)  # HIGH, LOW, DEVIATION, etc
    setpoint = db.Column(db.Float)
    deadband = db.Column(db.Float, default=0.0)
    
    # Configuração
    priority = db.Column(db.String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL
    is_active = db.Column(db.Boolean, default=True)
    auto_acknowledge = db.Column(db.Boolean, default=False)
    
    # Notificações
    email_enabled = db.Column(db.Boolean, default=False)
    email_recipients = db.Column(db.Text)  # JSON array
    
class Alarm(db.Model):
    """Instâncias de alarmes ativos"""
    id = db.Column(db.Integer, primary_key=True)
    alarm_definition_id = db.Column(db.Integer, db.ForeignKey('alarm_definition.id'))
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'))
    
    # Status do Alarme
    state = db.Column(db.String(20), nullable=False)  # ACTIVE, ACKNOWLEDGED, CLEARED
    priority = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    
    # Timestamps
    triggered_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(100))
    cleared_at = db.Column(db.DateTime)
    
    # Valores relacionados
    trigger_value = db.Column(db.Float)
    current_value = db.Column(db.Float)
