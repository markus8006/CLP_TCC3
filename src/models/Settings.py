"""Modelos relacionados à configuração persistente do sistema."""

from datetime import datetime, timezone

from src.app import db


class SystemSetting(db.Model):
    __tablename__ = "system_setting"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover - helper
        return f"<SystemSetting {self.key}={self.value}>"
