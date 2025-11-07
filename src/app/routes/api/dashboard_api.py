"""Dashboard centric API endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_login import login_required
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm
from src.models.Data import DataLog
from src.models.PLCs import PLC
from src.models.Registers import Register

from .common import plc_status, register_status, status_label


def build_dashboard_summary_payload() -> dict:
    totals_row = db.session.query(
        func.count(PLC.id),
        func.sum(case((PLC.is_online.is_(True), 1), else_=0)),
        func.sum(case((PLC.is_online.is_(False), 1), else_=0)),
        func.sum(case((PLC.is_active.is_(False), 1), else_=0)),
    ).one()

    totals = {
        "total_clps": totals_row[0] or 0,
        "online_clps": int(totals_row[1] or 0),
        "offline_clps": int(totals_row[2] or 0),
        "inactive_clps": int(totals_row[3] or 0),
        "total_registers": db.session.query(func.count(Register.id)).scalar() or 0,
        "active_alarms": db.session.query(func.count(Alarm.id)).filter(Alarm.state == "ACTIVE").scalar()
        or 0,
        "active_vlans": (
            db.session.query(func.count(func.distinct(PLC.vlan_id)))
            .filter(PLC.vlan_id.isnot(None))
            .scalar()
            or 0
        ),
        "logs_last_24h": (
            db.session.query(func.count(DataLog.id))
            .filter(DataLog.timestamp.isnot(None))
            .filter(DataLog.timestamp >= datetime.utcnow() - timedelta(hours=24))
            .scalar()
            or 0
        ),
    }

    horizon = datetime.utcnow() - timedelta(days=13)
    log_volume_query = (
        db.session.query(
            func.date(DataLog.timestamp).label("day"),
            func.count(DataLog.id),
        )
        .filter(DataLog.timestamp.isnot(None))
        .filter(DataLog.timestamp >= horizon)
        .group_by("day")
        .order_by("day")
    )
    log_volume = [
        {"date": day.isoformat() if hasattr(day, "isoformat") else str(day), "count": count}
        for day, count in log_volume_query
    ]

    alarms_by_priority_query = (
        db.session.query(Alarm.priority, func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE")
        .group_by(Alarm.priority)
    )
    alarms_by_priority = {
        (priority or "Sem prioridade"): count for priority, count in alarms_by_priority_query
    }

    offline_clps = (
        db.session.query(PLC)
        .options(selectinload(PLC.organization))
        .filter(PLC.is_active.is_(True), PLC.is_online.is_(False))
        .order_by(PLC.last_seen.asc())
        .limit(6)
        .all()
    )
    offline_payload = [
        {
            "id": plc.id,
            "name": plc.name,
            "ip": plc.ip_address,
            "vlan_id": plc.vlan_id,
            "last_seen": plc.last_seen.isoformat() if plc.last_seen else None,
            "reason": "Sem comunicação" if plc.last_seen else "Nunca conectado",
            "location": plc.organization.name if plc.organization else None,
        }
        for plc in offline_clps
    ]

    return {
        "totals": totals,
        "log_volume": log_volume,
        "alarms_by_priority": alarms_by_priority,
        "offline_clps": offline_payload,
    }


def build_dashboard_plc_payload() -> dict:
    alarm_by_plc = {
        plc_id: count
        for plc_id, count in db.session.query(Alarm.plc_id, func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE")
        .group_by(Alarm.plc_id)
    }

    latest_logs = {
        plc_id: ts
        for plc_id, ts in db.session.query(PLC.id, func.max(DataLog.timestamp))
        .join(DataLog, DataLog.plc_id == PLC.id, isouter=True)
        .group_by(PLC.id)
    }

    plcs = (
        db.session.query(PLC)
        .options(selectinload(PLC.organization))
        .order_by(PLC.name)
        .all()
    )

    payload = []
    for plc in plcs:
        status = plc_status(plc, alarm_by_plc)
        last_ts = latest_logs.get(plc.id)
        payload.append(
            {
                "id": plc.id,
                "name": plc.name,
                "ip": plc.ip_address,
                "status": status,
                "status_label": status_label(status),
                "alarm_count": int(alarm_by_plc.get(plc.id, 0)),
                "protocol": plc.protocol,
                "vlan_id": plc.vlan_id,
                "location": plc.organization.name if plc.organization else None,
                "last_read": last_ts.isoformat() if last_ts else None,
            }
        )

    return {"plcs": payload}


def build_plc_details_payload(plc_id: int) -> tuple[dict, int]:
    plc = (
        db.session.query(PLC)
        .options(
            selectinload(PLC.registers).selectinload(Register.alarms),
            selectinload(PLC.registers).selectinload(Register.alarm_definitions),
            selectinload(PLC.alarms),
            selectinload(PLC.organization),
        )
        .get(plc_id)
    )

    if plc is None:
        return {"message": "CLP não encontrado."}, 404

    register_ids = [register.id for register in plc.registers]
    alarm_by_register: dict[int, int] = {}
    if register_ids:
        alarm_by_register = {
            register_id: count
            for register_id, count in db.session.query(Alarm.register_id, func.count(Alarm.id))
            .filter(Alarm.state == "ACTIVE", Alarm.register_id.in_(register_ids))
            .group_by(Alarm.register_id)
        }

    plc_alarm_total = (
        db.session.query(func.count(Alarm.id))
        .filter(Alarm.state == "ACTIVE", Alarm.plc_id == plc.id)
        .scalar()
        or 0
    )

    status = plc_status(plc, {plc.id: plc_alarm_total})

    def _register_status_payload(register: Register) -> tuple[str, str]:
        reg_status = register_status(register, alarm_by_register)
        if reg_status == "online":
            key = "ok"
            label = "Operacional"
        elif reg_status == "alarm":
            key = "alarm"
            label = "Em alarme"
        elif reg_status == "inactive":
            key = "inactive"
            label = "Inativo"
        else:
            key = reg_status
            label = reg_status.title()
        return key, label

    register_payload = []
    for register in plc.registers:
        key, label = _register_status_payload(register)
        register_payload.append(
            {
                "id": register.id,
                "name": register.name,
                "status": key,
                "status_label": label,
                "tag": register.tag_name or register.tag,
                "address": register.address,
                "data_type": register.data_type,
                "unit": register.unit,
                "last_value": register.last_value,
                "last_read": register.last_read.isoformat() if register.last_read else None,
                "description": register.description,
                "normalized_address": register.normalized_address,
            }
        )

    last_log = (
        db.session.query(DataLog.timestamp)
        .filter(DataLog.plc_id == plc.id)
        .order_by(DataLog.timestamp.desc())
        .first()
    )

    location_label = plc.organization.name if plc.organization else None

    log_rows = (
        db.session.query(DataLog)
        .options(selectinload(DataLog.register))
        .filter(DataLog.plc_id == plc.id)
        .order_by(DataLog.timestamp.desc())
        .limit(20)
        .all()
    )

    log_payload = [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "register": log.register.name if log.register else None,
            "value": log.value_float,
            "quality": log.quality,
        }
        for log in log_rows
    ]

    alarm_rows = (
        db.session.query(Alarm)
        .options(selectinload(Alarm.register))
        .filter(Alarm.plc_id == plc.id)
        .order_by(Alarm.triggered_at.desc())
        .limit(20)
        .all()
    )

    alarm_payload = [
        {
            "id": alarm.id,
            "message": alarm.message,
            "priority": alarm.priority,
            "state": alarm.state,
            "register": alarm.register.name if alarm.register else None,
            "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
        }
        for alarm in alarm_rows
    ]

    payload = {
        "plc": {
            "id": plc.id,
            "name": plc.name,
            "status": status,
            "status_label": status_label(status),
            "protocol": plc.protocol,
            "ip_address": plc.ip_address,
            "vlan_id": plc.vlan_id,
            "location": location_label,
            "last_seen": plc.last_seen.isoformat() if plc.last_seen else None,
            "description": plc.description,
            "last_log": last_log[0].isoformat() if last_log and last_log[0] else None,
        },
        "registers": register_payload,
        "logs": log_payload,
        "alarms": alarm_payload,
    }

    return payload, 200


dashboard_api_bp = Blueprint("api_dashboard", __name__)


@dashboard_api_bp.route("/summary", methods=["GET"])
@login_required
def dashboard_summary():
    return jsonify(build_dashboard_summary_payload())


@dashboard_api_bp.route("/plcs", methods=["GET"])
@login_required
def dashboard_plc_collection():
    return jsonify(build_dashboard_plc_payload())


@dashboard_api_bp.route("/clps/<int:plc_id>", methods=["GET"])
@login_required
def dashboard_plc_details(plc_id: int):
    payload, status_code = build_plc_details_payload(plc_id)
    return jsonify(payload), status_code


__all__ = ["dashboard_api_bp", "build_dashboard_summary_payload", "build_dashboard_plc_payload", "build_plc_details_payload"]
