from datetime import datetime, timezone

from src.app import db


class AlarmDefinition(db.Model):
    __tablename__ = "alarm_definition"

    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey("plc.id"), nullable=False)
    register_id = db.Column(db.Integer, db.ForeignKey("register.id"), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    condition_type = db.Column(db.String(30), nullable=False, default="above")
    setpoint = db.Column(db.Float, nullable=True)
    threshold_low = db.Column(db.Float, nullable=True)
    threshold_high = db.Column(db.Float, nullable=True)
    deadband = db.Column(db.Float, default=0.0)

    priority = db.Column(db.String(20), default="MEDIUM")
    is_active = db.Column(db.Boolean, default=True)
    auto_acknowledge = db.Column(db.Boolean, default=False)
    email_enabled = db.Column(db.Boolean, default=False)
    severity = db.Column(db.Integer, default=3)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    plc = db.relationship(
        "PLC",
        backref=db.backref("alarm_definitions", cascade="all, delete-orphan"),
    )
    register = db.relationship("Register", back_populates="alarm_definitions")
    alarms = db.relationship(
        "Alarm",
        backref="definition",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AlarmDefinition id={self.id} name={self.name!r} plc_id={self.plc_id}>"


class Alarm(db.Model):
    __tablename__ = "alarm"

    id = db.Column(db.Integer, primary_key=True)
    alarm_definition_id = db.Column(
        db.Integer,
        db.ForeignKey("alarm_definition.id"),
        nullable=True,
        index=True,
    )
    plc_id = db.Column(db.Integer, db.ForeignKey("plc.id"), nullable=False, index=True)
    register_id = db.Column(
        db.Integer, db.ForeignKey("register.id"), nullable=True, index=True
    )

    state = db.Column(db.String(20), nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)

    triggered_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.String(100))
    cleared_at = db.Column(db.DateTime)

    trigger_value = db.Column(db.Float)
    current_value = db.Column(db.Float)

    last_updated_at = db.Column(db.DateTime, nullable=True)

    register = db.relationship("Register", back_populates="alarms")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Alarm id={self.id} state={self.state} plc_id={self.plc_id}>"
