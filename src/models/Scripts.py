"""Modelo de scripts customizados executados pelo runtime."""

from __future__ import annotations

from datetime import datetime, timezone

from src.app import db


class Script(db.Model):
    __tablename__ = "scripts"

    id = db.Column(db.Integer, primary_key=True)
    plc_id = db.Column(db.Integer, db.ForeignKey("plc.id"))
    name = db.Column(db.String(120), nullable=False)
    language = db.Column(db.String(40), nullable=False, default="python")
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    plc = db.relationship("PLC", back_populates="scripts")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Script id={self.id} plc={self.plc_id} name={self.name!r}>"


__all__ = ["Script"]
