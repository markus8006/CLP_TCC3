from src.app import db
from datetime import datetime

class SecurityEvent(db.Model):
    """Eventos de segurança detectados pelo sistema"""
    __tablename__ = 'security_event'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(15), nullable=False)
    user_agent = db.Column(db.Text)
    url = db.Column(db.Text, nullable=False)
    method = db.Column(db.String(10), nullable=False)
    threat_score = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<SecurityEvent {self.ip_address} - Score: {self.threat_score}>'
