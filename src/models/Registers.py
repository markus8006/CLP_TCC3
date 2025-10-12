from src.app import db
from datetime import datetime

class Register(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    
    # Identificação
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    tag = db.Column(db.String(50))  # Tag industrial
    
    # Configuração do Registrador
    address = db.Column(db.String(20), nullable=False)  # Pode ser numérico ou string
    register_type = db.Column(db.String(20), nullable=False)  # holding, input, coil, discrete
    data_type = db.Column(db.String(20), nullable=False)  # int16, float32, bool, etc
    length = db.Column(db.Integer, default=1)  # Para strings ou arrays
    
    # Processamento de Dados
    scale_factor = db.Column(db.Float, default=1.0)
    offset = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20))
    decimal_places = db.Column(db.Integer, default=2)
    
    # Limites e Alarmes
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    low_alarm = db.Column(db.Float)  # Alarme de valor baixo
    high_alarm = db.Column(db.Float)  # Alarme de valor alto
    
    # Configuração de Polling
    is_active = db.Column(db.Boolean, default=True)
    poll_rate = db.Column(db.Integer, default=1000)  # ms, override do PLC
    log_enabled = db.Column(db.Boolean, default=True)
    
    # Status
    last_value = db.Column(db.Text)  # JSON para valores complexos
    last_read = db.Column(db.DateTime)
    error_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
