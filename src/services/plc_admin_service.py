"""Serviços de apoio às operações administrativas sobre CLPs."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from src.app import db
from src.models.PLCs import PLC
from src.repository.PLC_repository import PLCRepo
from src.utils.tags import parse_tags


_PLC_MUTABLE_FIELDS: Iterable[str] = (
    "name",
    "description",
    "ip_address",
    "protocol",
    "port",
    "vlan_id",
    "subnet_mask",
    "gateway",
    "unit_id",
    "manufacturer",
    "model",
    "firmware_version",
    "is_active",
)


def _get_repo(session: Optional[Session]) -> PLCRepo:
    """Return a PLC repository bound to the provided session."""

    return PLCRepo(session=session or db.session)


def _extract_plc_kwargs(data: Dict[str, Any]) -> Dict[str, Any]:
    return {key: data.get(key) for key in _PLC_MUTABLE_FIELDS}


def create_plc(
    data: Dict[str, Any],
    *,
    actor: Optional[str] = None,
    source: str = "admin_ui",
    session: Optional[Session] = None,
) -> PLC:
    """Cria um novo PLC a partir dos dados fornecidos.

    Parameters
    ----------
    data:
        Dicionário com os valores do formulário. Pode conter ``tags`` como
        string ou lista.
    actor:
        Identificador do utilizador responsável pela operação.
    source:
        Origem textual usada para auditoria (por omissão ``admin_ui``).
    session:
        Sessão SQLAlchemy a utilizar. Quando ``None`` usa ``db.session``.

    Raises
    ------
    SQLAlchemyError
        Propagada quando ocorre erro de persistência (p.ex. ``IntegrityError``).
    """

    repo = _get_repo(session)
    payload = _extract_plc_kwargs(data)
    tags = parse_tags(data.get("tags"))

    plc = PLC(**payload)
    plc.set_tags(tags)

    if plc.is_active:
        plc.mark_active(actor=actor, source=source)
    else:
        plc.mark_inactive(actor=actor, source=source)

    return repo.add(plc, commit=True)


def update_plc(
    plc: PLC,
    data: Dict[str, Any],
    *,
    actor: Optional[str] = None,
    source: str = "admin_ui",
    session: Optional[Session] = None,
) -> PLC:
    """Atualiza um PLC existente com os dados informados."""

    repo = _get_repo(session)
    current = repo.session.merge(plc)
    previous_state = current.is_active

    for field, value in _extract_plc_kwargs(data).items():
        setattr(current, field, value)

    current.set_tags(parse_tags(data.get("tags")))

    state_changed = previous_state != current.is_active
    if state_changed:
        if current.is_active:
            current.mark_active(actor=actor, source=source)
        else:
            current.mark_inactive(actor=actor, source=source)

    repo.session.commit()
    return current


def delete_plc(plc: PLC, *, session: Optional[Session] = None) -> None:
    """Remove o PLC informado."""

    repo = _get_repo(session)
    repo.session.delete(repo.session.merge(plc))
    repo.session.commit()
