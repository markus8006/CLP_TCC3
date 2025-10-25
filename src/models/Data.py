# src/models/data_log.py
from src.app import db
from datetime import datetime, timezone
from sqlalchemy import Index, Boolean

class DataLog(db.Model):
    __tablename__ = 'data_log'
    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey('plc.id'), nullable=False, index=True)
    register_id = db.Column(db.Integer, db.ForeignKey('register.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    raw_value = db.Column(db.Text)
    value_float = db.Column(db.Float)
    value_int = db.Column(db.BigInteger)
    quality = db.Column(db.String(20))
    unit = db.Column(db.String(20))
    tags = db.Column(db.JSON)
    is_alarm = db.Column(Boolean, nullable=False, default=False, index=True)

    register = db.relationship("Register", back_populates="datalogs")

    __table_args__ = (
        Index('ix_data_plc_register_time', 'plc_id', 'register_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<DataLog plc={self.plc_id} reg={self.register_id} ts={self.timestamp} alarm={self.is_alarm}>"

