from src.app import db

class DataLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=False)
    
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)  # JSON para flexibilidade
    raw_value = db.Column(db.Text)  # Valor antes do processamento
    quality = db.Column(db.String(20), default='GOOD')  # GOOD, BAD, UNCERTAIN
    
    # Particionamento por tempo para performance
    __table_args__ = (
        db.Index('idx_datalog_time_plc', 'timestamp', 'plc_id'),
        db.Index('idx_datalog_time_register', 'timestamp', 'register_id'),
    )
