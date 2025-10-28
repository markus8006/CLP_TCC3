"""Models related to the factory layout designer."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.app import db


class FactoryLayout(db.Model):
    """Persisted representation of the factory layout canvas.

    The layout schema stores the positions of VLANs, PLCs and registers as a
    JSON document. Only a handful of layouts are expected to exist, therefore a
    very small table backed by JSON columns is sufficient.
    """

    __tablename__ = "factory_layout"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, default="default")
    description = db.Column(db.Text)
    layout_schema = db.Column(db.JSON, default=dict)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def touch_layout(self, schema: Dict[str, Any], *, actor_id: Optional[int] = None) -> None:
        """Replace the stored layout schema with ``schema``.

        Parameters
        ----------
        schema:
            Dictionary with the layout definition. The content is validated at
            the API level to keep the model thin.
        actor_id:
            Optional identifier of the user that performed the change. The
            ``updated_by`` attribute is filled when provided.
        """

        if schema is None:
            schema = {}
        self.layout_schema = schema
        if actor_id is not None:
            self.updated_by = actor_id
        if self.created_by is None and actor_id is not None:
            self.created_by = actor_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "layout_schema": self.layout_schema or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
