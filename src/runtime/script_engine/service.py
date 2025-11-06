"""Persistência e gestão de scripts customizados."""

from __future__ import annotations

from typing import List, Optional

from src.app.extensions import db
from src.models.Scripts import Script


class ScriptEngine:
    """Camada simples para guardar scripts associados aos CLPs."""

    SUPPORTED_LANGUAGES = {
        "python": "Python",
        "st": "Structured Text",
        "ladder": "Ladder",
    }

    def list_scripts(self, plc_id: int) -> List[Script]:
        return (
            Script.query.filter_by(plc_id=plc_id)
            .order_by(Script.updated_at.desc())
            .all()
        )

    def get_script(self, script_id: int) -> Optional[Script]:
        return Script.query.get(script_id)

    def save_script(self, *, plc_id: int, name: str, language: str, content: str) -> Script:
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"Linguagem não suportada: {language}")

        script = Script.query.filter_by(plc_id=plc_id, name=name).first()
        if script is None:
            script = Script(plc_id=plc_id, name=name)
            db.session.add(script)

        script.language = language
        script.content = content
        db.session.commit()
        return script

    def delete_script(self, script_id: int) -> None:
        script = Script.query.get(script_id)
        if script is None:
            return
        db.session.delete(script)
        db.session.commit()


__all__ = ["ScriptEngine"]
