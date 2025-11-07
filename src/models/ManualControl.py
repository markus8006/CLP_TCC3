"""Models dedicated to manual commands executed from the HMI."""

from __future__ import annotations

from datetime import datetime, timezone

from src.app import db


class ManualCommand(db.Model):
    """Registers every manual intervention triggered via the HMI."""

    __tablename__ = "manual_command"

    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey("plc.id"), nullable=False, index=True)
    register_id = db.Column(
        db.Integer, db.ForeignKey("register.id"), nullable=False, index=True
    )
    command_type = db.Column(db.String(40), nullable=False)
    value_numeric = db.Column(db.Float)
    value_text = db.Column(db.Text)
    executed_by = db.Column(db.String(120), nullable=False)
    note = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending")
    reviewer_note = db.Column(db.Text)
    approved_by = db.Column(db.String(120))
    approved_at = db.Column(db.DateTime(timezone=True))
    rejected_by = db.Column(db.String(120))
    rejected_at = db.Column(db.DateTime(timezone=True))
    dispatched_by = db.Column(db.String(120))
    dispatched_at = db.Column(db.DateTime(timezone=True))
    execution_note = db.Column(db.Text)
    datalog_id = db.Column(db.Integer, db.ForeignKey("data_log.id"))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    datalog = db.relationship("DataLog")

    register = db.relationship("Register", backref="manual_commands")
    plc = db.relationship("PLC", backref="manual_commands")

    def as_dict(self) -> dict[str, object]:
        """Return a serialisable representation for APIs."""

        return {
            "id": self.id,
            "plc_id": self.plc_id,
            "register_id": self.register_id,
            "command_type": self.command_type,
            "value_numeric": self.value_numeric,
            "value_text": self.value_text,
            "executed_by": self.executed_by,
            "note": self.note,
            "status": self.status,
            "reviewer_note": self.reviewer_note,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_by": self.rejected_by,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "dispatched_by": self.dispatched_by,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "execution_note": self.execution_note,
            "datalog_id": self.datalog_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__all__ = ["ManualCommand"]
