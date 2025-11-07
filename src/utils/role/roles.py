from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import abort, flash, has_request_context, jsonify, request
from flask_login import current_user

from src.app.extensions import login_manager

RoleType = Any


def _normalize_role_name(min_role: RoleType) -> str:
    if hasattr(min_role, "value"):
        return str(getattr(min_role, "value"))
    return str(min_role)


def require_role(min_role: RoleType, *, format: str = "html"):
    if format not in {"html", "json"}:
        raise ValueError(f"Formato desconhecido: {format}")

    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    if current_user.has_permission(min_role):
        return None

    role_name = _normalize_role_name(min_role)

    if format == "json":
        payload = {
            "error": "forbidden",
            "message": "Permissão insuficiente para aceder ao recurso solicitado.",
            "required_role": role_name,
        }
        return jsonify(payload), 403

    flash(f"O usuario {current_user} não tem permissão suficiente", "warning")
    abort(403)


def _infer_response_format() -> str:
    if not has_request_context():
        return "html"

    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    if best == "application/json":
        return "json"
    return "html"


def role_required(min_role: RoleType, *, format: str | None = None) -> Callable:
    def wrapper(fn: Callable) -> Callable:
        @wraps(fn)
        def decorator_view(*args: Any, **kwargs: Any):
            response_format = format or _infer_response_format()
            result = require_role(min_role, format=response_format)
            if result is not None:
                return result
            return fn(*args, **kwargs)

        return decorator_view

    return wrapper
