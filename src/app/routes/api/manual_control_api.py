"""Manual control and HMI API endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm
from src.models.Data import DataLog
from src.models.ManualControl import ManualCommand
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.services.manual_control_service import ManualControlService
from src.utils.role.roles import role_required

from .common import plc_status, register_status, status_label, vlan_identifier, vlan_label

manual_control_service = ManualControlService()

manual_control_api_bp = Blueprint("api_manual_control", __name__)


def build_hmi_overview_payload() -> dict:
    alarm_by_plc = {
        plc_id: count
        for plc_id, count in db.session.query(Alarm.plc_id, func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE")
        .group_by(Alarm.plc_id)
    }

    alarm_by_register = {
        register_id: count
        for register_id, count in db.session.query(Alarm.register_id, func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE", Alarm.register_id.isnot(None))
        .group_by(Alarm.register_id)
    }

    plcs = (
        db.session.query(PLC)
        .options(selectinload(PLC.registers))
        .order_by(PLC.vlan_id.nullsfirst(), PLC.name)
        .all()
    )

    areas: dict[str, dict] = {}
    register_options: list[dict[str, object]] = []
    for plc in plcs:
        area_key = vlan_identifier(plc.vlan_id)
        area = areas.setdefault(
            area_key,
            {
                "id": area_key,
                "label": vlan_label(plc.vlan_id),
                "plcs": [],
            },
        )

        registers_payload = []
        for register in sorted(plc.registers, key=lambda item: item.name.lower()):
            if not register.is_active:
                continue
            status = register_status(register, alarm_by_register)
            registers_payload.append(
                {
                    "id": register.id,
                    "name": register.name,
                    "tag": register.tag or register.tag_name,
                    "last_value": register.last_value,
                    "unit": register.unit,
                    "status": status,
                    "last_read": register.last_read.isoformat() if register.last_read else None,
                }
            )
            register_options.append(
                {
                    "id": register.id,
                    "label": f"{plc.name} · {register.name}",
                    "plc_id": plc.id,
                    "status": status,
                }
            )

        area["plcs"].append(
            {
                "id": plc.id,
                "name": plc.name,
                "protocol": plc.protocol,
                "status": plc_status(plc, alarm_by_plc),
                "registers": registers_payload,
            }
        )

    totals_row = db.session.query(
        func.count(PLC.id),
        func.sum(case((PLC.is_online.is_(True), 1), else_=0)),
    ).one()

    total_clps = totals_row[0] or 0
    online_clps = int(totals_row[1] or 0)
    availability = (online_clps / total_clps * 100) if total_clps else 0.0

    horizon_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    report_metrics = {
        "clp_availability": round(availability, 1),
        "active_alarms": db.session.query(func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE")
        .scalar()
        or 0,
        "manual_commands_24h": db.session.query(func.count(ManualCommand.id))
        .filter(ManualCommand.created_at >= horizon_24h)
        .scalar()
        or 0,
        "logs_last_24h": db.session.query(func.count(DataLog.id))
        .filter(DataLog.timestamp >= horizon_24h)
        .scalar()
        or 0,
    }

    return {
        "areas": list(areas.values()),
        "register_options": register_options,
        "report_metrics": report_metrics,
    }


@manual_control_api_bp.route("/overview", methods=["GET"])
@login_required
def hmi_overview():
    return jsonify(build_hmi_overview_payload())


@manual_control_api_bp.route("/alarms", methods=["GET"])
@login_required
def hmi_active_alarms():
    alarms = (
        db.session.query(Alarm)
        .options(selectinload(Alarm.plc), selectinload(Alarm.register))
        .filter(Alarm.state == "ACTIVE")
        .order_by(Alarm.priority.desc(), Alarm.triggered_at.desc())
        .limit(50)
        .all()
    )

    now = datetime.now(timezone.utc)
    payload = []
    for alarm in alarms:
        payload.append(
            {
                "id": alarm.id,
                "priority": alarm.priority.lower() if alarm.priority else "medium",
                "message": alarm.message,
                "plc": alarm.plc.name if alarm.plc else None,
                "register": alarm.register.name if alarm.register else None,
                "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
                "age_seconds": (
                    (now - alarm.triggered_at).total_seconds()
                    if alarm.triggered_at
                    else None
                ),
            }
        )

    return jsonify({"alarms": payload})


@manual_control_api_bp.route("/manual-commands", methods=["GET"])
@login_required
def hmi_manual_history():
    commands = manual_control_service.recent_commands(limit=25)
    return jsonify({"commands": [command.as_dict() for command in commands]})


@manual_control_api_bp.route("/register/<int:register_id>/trend", methods=["GET"])
@login_required
def hmi_register_trend(register_id: int):
    register = db.session.query(Register).filter(Register.id == register_id).first()
    if not register:
        return jsonify({"message": "Registrador não encontrado"}), 404

    logs = (
        db.session.query(DataLog)
        .filter(DataLog.register_id == register_id)
        .filter(DataLog.timestamp.isnot(None))
        .order_by(DataLog.timestamp.desc())
        .limit(200)
        .all()
    )
    logs.reverse()

    points = [
        {
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "value": log.value_float,
            "raw": log.raw_value,
            "quality": log.quality,
        }
        for log in logs
    ]

    return jsonify(
        {
            "register": {
                "id": register.id,
                "name": register.name,
                "unit": register.unit,
            },
            "points": points,
        }
    )


@manual_control_api_bp.route("/register/<int:register_id>/manual", methods=["POST"])
@login_required
@role_required("operator")
def hmi_execute_manual_command(register_id: int):
    payload = request.get_json(silent=True) or {}
    command_type = payload.get("command_type", "setpoint")

    try:
        value = payload.get("value")
        value_numeric = float(value) if value is not None else None
    except (TypeError, ValueError):
        return jsonify({"message": "Valor numérico inválido."}), 400

    note = payload.get("note")

    try:
        result = manual_control_service.execute_command(
            register_id=register_id,
            command_type=command_type,
            value=value_numeric,
            value_text=str(value) if value is not None else None,
            executed_by=getattr(current_user, "username", None),
            note=note,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return jsonify(
        {
            "command": result.command.as_dict(),
            "datalog_id": result.datalog.id,
        }
    )


__all__ = [
    "manual_control_api_bp",
    "build_hmi_overview_payload",
]
