"""Historian export endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import login_required

from src.services.historian_sync_service import HistorianSyncService
from src.utils.role.roles import role_required

historian_sync_service = HistorianSyncService()

historian_api_bp = Blueprint("api_historian", __name__)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError as exc:  # pragma: no cover - simple validation
        raise ValueError("Formato de data inválido. Use ISO 8601.") from exc


@historian_api_bp.route("/export", methods=["POST"])
@login_required
@role_required("admin")
def historian_export():
    payload = request.get_json(silent=True) or {}

    try:
        start = _parse_dt(payload.get("start"))
        end = _parse_dt(payload.get("end"))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    result = historian_sync_service.export_snapshot(start=start, end=end)

    return jsonify(
        {
            "file": str(result.file_path),
            "rows": result.rows,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
        }
    )


__all__ = ["historian_api_bp"]
