"""Serviços administrativos relacionados a registradores."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.app import db
from src.models.Registers import Register
from src.repository.Registers_repository import RegisterRepo


def _get_repo(session: Optional[Session]) -> RegisterRepo:
    return RegisterRepo(session=session or db.session)


def create_register(
    data: Dict[str, Any],
    *,
    session: Optional[Session] = None,
) -> Register:
    """Cria e persiste um registrador a partir dos dados fornecidos."""

    repo = _get_repo(session)
    payload: Dict[str, Any] = {
        "plc_id": data.get("plc_id"),
        "name": data.get("name"),
        "description": data.get("description"),
        "address": data.get("address"),
        "register_type": data.get("register_type"),
        "data_type": data.get("data_type"),
        "length": data.get("length") or 1,
        "unit": data.get("unit"),
        "scale_factor": data.get("scale_factor") if data.get("scale_factor") is not None else 1.0,
        "offset": data.get("offset") if data.get("offset") is not None else 0.0,
        "tag": data.get("tag"),
    }

    register = Register(**payload)
    return repo.add(register, commit=True)


def delete_register(register: Register, *, session: Optional[Session] = None) -> None:
    repo = _get_repo(session)
    repo.session.delete(repo.session.merge(register))
    repo.session.commit()
