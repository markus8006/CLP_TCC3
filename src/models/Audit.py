from src.app import db
from datetime import datetime, timezone

class AuditLog(db.Model):
    """Log de todas as ações no sistema"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Ação realizada
    action = db.Column(db.String(50), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN
    resource_type = db.Column(db.String(50), nullable=False)  # PLC, USER, REGISTER
    resource_id = db.Column(db.Integer)
    
    # Detalhes
    description = db.Column(db.Text)
    old_values = db.Column(db.Text)  # JSON dos valores anteriores
    new_values = db.Column(db.Text)  # JSON dos novos valores
    
    # Contexto
    ip_address = db.Column(db.String(15))
    user_agent = db.Column(db.Text)
    
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))
