# models/register.py
from src.app import db
from datetime import datetime, timezone

class Register(db.Model):
    __tablename__ = 'register'   # >>> importante: usar nome consistente para FK
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False)
    slave = db.Column(db.Integer, default=1)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    tag = db.Column(db.String(50))

    address = db.Column(db.String(50), nullable=False)  # mantém string (p.ex. "40001" ou "40001.1")
    register_type = db.Column(db.String(20), nullable=False)
    data_type = db.Column(db.String(20), nullable=False)
    length = db.Column(db.Integer, default=1)

    scale_factor = db.Column(db.Float, default=1.0)
    offset = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20))
    decimal_places = db.Column(db.Integer, default=2)

    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    low_alarm = db.Column(db.Float)
    high_alarm = db.Column(db.Float)

    is_active = db.Column(db.Boolean, default=True)
    poll_rate = db.Column(db.Integer, default=1000)  # ms
    log_enabled = db.Column(db.Boolean, default=True)

    last_value = db.Column(db.Text)  # pode guardar JSON como fallback
    last_read = db.Column(db.DateTime)
    error_count = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Register id={self.id} plc={self.plc_id} name={self.name} addr={self.address}>"
