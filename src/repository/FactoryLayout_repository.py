"""Repository utilities for the factory layout designer."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.app import db
from src.models.FactoryLayout import FactoryLayout
from src.repository.Base_repository import BaseRepo


class FactoryLayoutRepository(BaseRepo):
    """Handle CRUD operations for :class:`FactoryLayout`."""

    DEFAULT_LAYOUT_NAME = "default"

    def __init__(self):
        super().__init__(FactoryLayout)

    @classmethod
    def get_or_create_default(cls) -> FactoryLayout:
        repo = cls()
        layout = repo.session.query(FactoryLayout).filter_by(
            name=cls.DEFAULT_LAYOUT_NAME
        ).first()
        if layout is None:
            layout = FactoryLayout(name=cls.DEFAULT_LAYOUT_NAME, layout_schema={})
            repo.session.add(layout)
            repo.session.commit()
        return layout

    @classmethod
    def update_layout(
        cls, schema: Dict[str, Any], *, actor_id: Optional[int] = None
    ) -> FactoryLayout:
        layout = cls.get_or_create_default()
        layout.touch_layout(schema, actor_id=actor_id)
        db.session.add(layout)
        db.session.commit()
        return layout

    @classmethod
    def delete_default(cls) -> None:
        layout = cls.get_or_create_default()
        db.session.delete(layout)
        db.session.commit()
