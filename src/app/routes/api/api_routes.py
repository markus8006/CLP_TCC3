import asyncio
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, make_response, request
from flask_login import current_user, login_required
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Data import DataLog
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.repository.FactoryLayout_repository import FactoryLayoutRepository
from src.repository.PLC_repository import Plcrepo
from src.runtime.script_engine import ScriptEngine
from src.services.register_import_service import RegisterImportExportService
from src.services.tag_discovery_service import discover_tags as discover_tags_async
from src.utils.role.roles import role_required
from src.utils.tags import normalize_tag

api_bp = Blueprint("apii", __name__)

STATUS_LABELS = {
    "online": "Online",
    "offline": "Offline",
    "alarm": "Em alarme",
    "inactive": "Inativo",
}

register_service = RegisterImportExportService()
script_engine = ScriptEngine()


def _await(coro):
    """Executa uma corrotina em contexto síncrono do Flask."""

    return asyncio.run(coro)


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())


def _plc_status(plc, alarm_by_plc: dict) -> str:
    if not plc.is_active:
        return "inactive"
    if alarm_by_plc.get(plc.id, 0) > 0:
        return "alarm"
    if plc.is_online:
        return "online"
    return "offline"


def _register_status(register, alarm_by_register: dict) -> str:
    if not register.is_active:
        return "inactive"
    if alarm_by_register.get(register.id, 0) > 0:
        return "alarm"
    return "online"


def _vlan_identifier(vlan_id) -> str:
    return "vlan-unset" if vlan_id is None else f"vlan-{vlan_id}"


def _vlan_label(vlan_id) -> str:
    return "Rede Local" if vlan_id is None else f"VLAN {vlan_id}"


def _vlan_value_from_key(key: str):
    if key == "vlan-unset":
        return None
    try:
        return int(key.split("-", 1)[1])
    except (IndexError, ValueError):
        return None


@api_bp.route("/tag-discovery/<protocol>", methods=["POST"])
@login_required
def api_tag_discovery(protocol: str):
    params = request.get_json(silent=True) or {}
    try:
        tags = _await(discover_tags_async(protocol, params))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:  # pragma: no cover - depende de libs externas
        return jsonify({"message": str(exc)}), 500

    return jsonify({"tags": tags})


@api_bp.route("/get/data/clp/<ip>", methods=["GET"])
@login_required
def get_data_optimized(ip):
    vlan_id = request.args.get("vlan", type=int)
    # Carrega o CLP e todas as relações com eficiência (selectinload evita N+1 queries)
    query = (
        db.session.query(PLC)
        .options(
            selectinload(PLC.registers)
            .selectinload(Register.datalogs),
            selectinload(PLC.registers)
            .selectinload(Register.alarms),
            selectinload(PLC.registers)
            .selectinload(Register.alarm_definitions)
        )
        .filter(PLC.ip_address == ip, PLC.is_active == True)
    )
    if vlan_id is not None:
        query = query.filter(PLC.vlan_id == vlan_id)

    clp = query.first()

    if not clp:
        return jsonify({"error": "CLP not found"}), 404

    result = {
        "clp_id": clp.id,
        "registers": {},
        "data": [],
        "alarms": [],
        "definitions_alarms": []
    }

    for register in filter(lambda r: r.is_active, clp.registers):
        result["registers"][register.id] = register.name

        # 1️⃣ Últimos 30 DataLogs (ordenados por timestamp desc)
        sorted_logs = sorted(register.datalogs, key=lambda d: d.timestamp or 0, reverse=True)[:30]
        result["data"].extend([
            {
                "id": d.id,
                "register_id": d.register_id,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                "value_float": d.value_float,
                "quality": d.quality,
            }
            for d in sorted_logs
        ])

        # 2️⃣ Alarmes ativos
        result["alarms"].extend([
            {
                "id": a.id,
                "plc_id": a.plc_id,
                "register_id": a.register_id,
                "state": a.state,
                "priority": a.priority,
                "message": a.message,
            }
            for a in register.alarms if a.state == "ACTIVE"
        ])

        # 3️⃣ Definições de alarmes ativas
        result["definitions_alarms"].extend([
            {
                "id": ad.id,
                "register_id": register.id,
                "name": ad.name,
                "condition_type": ad.condition_type,
                "threshold_low": ad.threshold_low,
                "threshold_high": ad.threshold_high,
                "setpoint": ad.setpoint,
            }
            for ad in register.alarm_definitions if ad.is_active
        ])

    return jsonify(result), 200


@api_bp.route("/dashboard/summary", methods=["GET"])
@login_required
def dashboard_summary():
    """Aggregated metrics used by the industrial dashboard."""

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
        "active_alarms": db.session.query(func.count(Alarm.id)).filter(Alarm.state == "ACTIVE").scalar() or 0,
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

    return jsonify(
        {
            "totals": totals,
            "log_volume": log_volume,
            "alarms_by_priority": alarms_by_priority,
            "offline_clps": offline_payload,
        }
    )


@api_bp.route("/dashboard/plcs", methods=["GET"])
@login_required
def dashboard_plc_collection():
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
        status = _plc_status(plc, alarm_by_plc)
        last_ts = latest_logs.get(plc.id)
        payload.append(
            {
                "id": plc.id,
                "name": plc.name,
                "ip": plc.ip_address,
                "status": status,
                "status_label": _status_label(status),
                "alarm_count": int(alarm_by_plc.get(plc.id, 0)),
                "protocol": plc.protocol,
                "vlan_id": plc.vlan_id,
                "location": plc.organization.name if plc.organization else None,
                "last_read": last_ts.isoformat() if last_ts else None,
            }
        )

    return jsonify({"plcs": payload})


@api_bp.route("/dashboard/layout", methods=["GET"])
@login_required
def dashboard_layout():
    layout_record = FactoryLayoutRepository.get_or_create_default()
    layout_schema = layout_record.layout_schema or {}
    nodes = list(layout_schema.get("nodes", []))
    connections = list(layout_schema.get("connections", []))

    node_by_id = {
        node.get("id"): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }

    def ensure_position(node, fallback_index: int) -> None:
        position = node.get("position") or {}
        if not isinstance(position, dict) or "x" not in position or "y" not in position:
            column_count = 4
            spacing_x = 240
            spacing_y = 180
            x = 60 + (fallback_index % column_count) * spacing_x
            y = 60 + (fallback_index // column_count) * spacing_y
            node["position"] = {"x": x, "y": y}

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
        .options(selectinload(PLC.registers), selectinload(PLC.organization))
        .order_by(PLC.vlan_id.nullslast(), PLC.name)
        .all()
    )

    registers_position_tracker = {}
    fallback_counter = len(node_by_id)
    connection_set = {
        (conn.get("source"), conn.get("target"))
        for conn in connections
        if isinstance(conn, dict)
    }

    vlan_status_counts = {}
    vlan_summary_data = {}

    for plc in plcs:
        vlan_key = _vlan_identifier(plc.vlan_id)
        vlan_node = node_by_id.get(vlan_key)
        if vlan_node is None:
            vlan_node = {
                "id": vlan_key,
                "type": "vlan",
            }
            ensure_position(vlan_node, fallback_counter)
            fallback_counter += 1
            nodes.append(vlan_node)
            node_by_id[vlan_key] = vlan_node

        vlan_metadata = vlan_node.setdefault("metadata", {})
        vlan_metadata["vlan_id"] = plc.vlan_id
        tracked_plcs = vlan_metadata.setdefault("plcs", [])
        if plc.id not in tracked_plcs:
            tracked_plcs.append(plc.id)

        vlan_node.update(
            {
                "label": _vlan_label(plc.vlan_id),
                "meta_line": f"{len(tracked_plcs)} CLPs",
            }
        )

        plc_node_id = f"plc-{plc.id}"
        plc_node = node_by_id.get(plc_node_id)
        if plc_node is None:
            plc_node = {"id": plc_node_id, "type": "plc"}
            ensure_position(plc_node, fallback_counter)
            fallback_counter += 1
            nodes.append(plc_node)
            node_by_id[plc_node_id] = plc_node

        status = _plc_status(plc, alarm_by_plc)

        location_label = plc.organization.name if plc.organization else None

        plc_node.update(
            {
                "label": plc.name or f"PLC {plc.id}",
                "meta_line": f"{plc.ip_address} · VLAN {plc.vlan_id or '-'}",
                "location_label": location_label,
                "status": status,
                "status_label": _status_label(status),
                "metadata": {
                    "plc_id": plc.id,
                    "ip_address": plc.ip_address,
                    "vlan_id": plc.vlan_id,
                    "location": location_label,
                    "location_label": location_label,
                },
            }
        )

        vlan_counts = vlan_status_counts.setdefault(vlan_key, {"online": 0, "offline": 0, "alarm": 0, "inactive": 0})
        vlan_counts[status] += 1

        if (vlan_key, plc_node_id) not in connection_set:
            connections.append({"source": vlan_key, "target": plc_node_id, "type": "network"})
            connection_set.add((vlan_key, plc_node_id))

        register_slots = registers_position_tracker.setdefault(plc.id, 0)

        for register in plc.registers:
            register_node_id = f"register-{register.id}"
            register_node = node_by_id.get(register_node_id)
            if register_node is None:
                register_node = {"id": register_node_id, "type": "register"}
                # Position registers around the PLC in a radial grid
                base_position = plc_node.get("position", {"x": 0, "y": 0})
                slot = register_slots
                offset_x = 180 + (slot % 3) * 140
                offset_y = (slot // 3) * 90
                register_node["position"] = {
                    "x": base_position.get("x", 0) + offset_x,
                    "y": base_position.get("y", 0) + offset_y,
                }
                register_slots += 1
                registers_position_tracker[plc.id] = register_slots
                nodes.append(register_node)
                node_by_id[register_node_id] = register_node

            reg_status = _register_status(register, alarm_by_register)
            register_node.update(
                {
                    "label": register.name,
                    "meta_line": register.tag or register.address,
                    "status": reg_status,
                    "status_label": _status_label(reg_status),
                    "metadata": {
                        "register_id": register.id,
                        "plc_id": plc.id,
                    },
                }
            )

            if (plc_node_id, register_node_id) not in connection_set:
                connections.append(
                    {"source": plc_node_id, "target": register_node_id, "type": "io"}
                )
                connection_set.add((plc_node_id, register_node_id))

    # Update VLAN meta information once all CLPs were processed
    for vlan_key, counts in vlan_status_counts.items():
        vlan_node = node_by_id.get(vlan_key)
        if not vlan_node:
            continue
        if counts["alarm"] > 0:
            status = "alarm"
        elif counts["offline"] > 0:
            status = "offline"
        elif counts["online"] > 0:
            status = "online"
        else:
            status = "inactive"

        vlan_node["status"] = status
        vlan_node["status_label"] = _status_label(status)
        vlan_node.setdefault("metadata", {})["plc_totals"] = counts
        vlan_summary_data[vlan_key] = {"status": status, "counts": counts.copy()}

    layout_payload = {
        "nodes": nodes,
        "connections": connections,
    }

    vlan_summary = {}
    for key, summary in vlan_summary_data.items():
        vlan_value = _vlan_value_from_key(key)
        label = _vlan_label(vlan_value)
        metadata = node_by_id.get(key, {}).get("metadata", {})
        vlan_summary[label] = {
            "status": summary["status"],
            "status_label": _status_label(summary["status"]),
            "plc_count": sum(summary["counts"].values()),
            "plcs": metadata.get("plcs", []),
        }

    return jsonify(
        {
            "layout": layout_payload,
            "vlan_summary": vlan_summary,
            "generated_at": datetime.utcnow().isoformat(),
        }
    )


@api_bp.route("/dashboard/layout", methods=["PUT"])
@login_required
@role_required("admin")
def update_dashboard_layout():
    payload = request.get_json(silent=True) or {}
    nodes = payload.get("nodes")
    connections = payload.get("connections")

    if not isinstance(nodes, list) or not isinstance(connections, list):
        return (
            jsonify({"message": "Estrutura inválida. Esperado 'nodes' e 'connections'."}),
            400,
        )

    sanitized_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id or not node_type:
            continue
        position = node.get("position") or {}
        sanitized_nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "position": {
                    "x": float(position.get("x", 0)),
                    "y": float(position.get("y", 0)),
                },
            }
        )

    sanitized_connections = []
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        source = connection.get("source")
        target = connection.get("target")
        if not source or not target:
            continue
        sanitized_connections.append(
            {
                "source": source,
                "target": target,
                "type": connection.get("type", "link"),
            }
        )

    FactoryLayoutRepository.update_layout(
        {"nodes": sanitized_nodes, "connections": sanitized_connections},
        actor_id=current_user.id,
    )

    return dashboard_layout()


@api_bp.route("/dashboard/clps/<int:plc_id>", methods=["GET"])
@login_required
def dashboard_plc_details(plc_id: int):
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
        return jsonify({"message": "CLP não encontrado."}), 404

    register_ids = [register.id for register in plc.registers]
    alarm_by_register = {}
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

    status = _plc_status(plc, {plc.id: plc_alarm_total})

    def _register_status_payload(register):
        reg_status = _register_status(register, alarm_by_register)
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
        .filter(DataLog.plc_id == plc.id)
        .filter(DataLog.timestamp.isnot(None))
        .order_by(DataLog.timestamp.desc())
        .limit(200)
        .all()
    )

    log_entries = []
    telemetry = {}
    for row in log_rows:
        payload = {
            "id": row.id,
            "register_id": row.register_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "value": row.value_float,
            "quality": row.quality,
        }
        log_entries.append(payload)

        if row.register_id is not None:
            bucket = telemetry.setdefault(str(row.register_id), [])
            bucket.append(payload)

    for bucket in telemetry.values():
        bucket.reverse()

    return jsonify(
        {
            "id": plc.id,
            "name": plc.name,
            "ip_address": plc.ip_address,
            "vlan_id": plc.vlan_id,
            "protocol": plc.protocol,
            "status": status,
            "status_label": _status_label(status),
            "last_seen": plc.last_seen.isoformat() if plc.last_seen else None,
            "last_log": last_log[0].isoformat() if last_log else None,
            "active_alarm_count": int(plc_alarm_total),
            "register_count": len(plc.registers),
            "location": location_label,
            "location_label": location_label,
            "registers": register_payload,
            "logs": log_entries,
            "telemetry": telemetry,
        }
    )


@api_bp.route("/clps/<ip>/tags", methods=["POST"])
@login_required
def add_tag(ip):
    vlan_id = request.args.get("vlan", type=int)
    plc = Plcrepo.get_by_ip(ip, vlan_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    payload = request.get_json(silent=True) or {}
    raw_tag = (payload.get("tag") or "").strip()
    if not raw_tag:
        return jsonify({"message": "Informe uma tag."}), 400

    tag = normalize_tag(raw_tag)
    if not tag:
        return jsonify({"message": "Tag inválida."}), 400

    current_tags = plc.tags_as_list()
    if tag in current_tags:
        return jsonify({"tag": tag, "tags": current_tags, "message": "Tag já associada."}), 200

    current_tags.append(tag)
    Plcrepo.update_tags(plc, current_tags)
    return jsonify({"tag": tag, "tags": current_tags}), 201


@api_bp.route("/clps/<ip>/tags/<tag>", methods=["DELETE"])
@login_required
def remove_tag(ip, tag):
    vlan_id = request.args.get("vlan", type=int)
    plc = Plcrepo.get_by_ip(ip, vlan_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    normalized = normalize_tag(tag)
    current_tags = plc.tags_as_list()
    if normalized not in current_tags:
        return jsonify({"message": "Tag não encontrada."}), 404

    updated = [t for t in current_tags if t != normalized]
    Plcrepo.update_tags(plc, updated)
    return jsonify({"tag": normalized, "tags": updated}), 200


@api_bp.route("/registers/import", methods=["POST"])
@login_required
def import_registers():
    clp_id = request.form.get("clp_id", type=int) or request.args.get("clp_id", type=int)
    if not clp_id:
        return jsonify({"message": "Informe o clp_id."}), 400

    file = request.files.get("file")
    if file is None:
        return jsonify({"message": "Envie um ficheiro CSV ou XLSX."}), 400

    plc = db.session.get(PLC, clp_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    try:
        frame = register_service.dataframe_from_file(file, file.filename)
    except Exception as exc:  # pragma: no cover - parsing externo
        return jsonify({"message": f"Não foi possível ler o ficheiro: {exc}"}), 400

    created, errors = register_service.import_dataframe(frame, plc=plc, protocol=plc.protocol)
    return jsonify({"created": created, "errors": errors}), 201


@api_bp.route("/registers/export", methods=["GET"])
@login_required
def export_registers():
    clp_id = request.args.get("clp_id", type=int)
    if not clp_id:
        return jsonify({"message": "Informe o clp_id."}), 400

    plc = db.session.get(PLC, clp_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    registers = Register.query.filter_by(plc_id=clp_id).order_by(Register.name).all()
    frame = register_service.export_dataframe(registers)

    file_format = request.args.get("format", "csv").lower()
    if file_format not in {"csv", "xlsx"}:
        file_format = "csv"

    data, mime = register_service.export_to_bytes(frame, file_format=file_format)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"registers_plc_{clp_id}_{timestamp}.{file_format}"

    response = make_response(data)
    response.headers["Content-Type"] = mime
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@api_bp.route("/plcs/<int:plc_id>/scripts", methods=["GET"])
@login_required
def list_plc_scripts(plc_id: int):
    plc = db.session.get(PLC, plc_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    scripts = script_engine.list_scripts(plc_id)
    return jsonify(
        {
            "languages": script_engine.SUPPORTED_LANGUAGES,
            "scripts": [
                {
                    "id": script.id,
                    "name": script.name,
                    "language": script.language,
                    "content": script.content,
                    "updated_at": script.updated_at.isoformat() if script.updated_at else None,
                }
                for script in scripts
            ],
        }
    )


@api_bp.route("/plcs/<int:plc_id>/scripts", methods=["POST"])
@login_required
def save_plc_script(plc_id: int):
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    language = (payload.get("language") or "python").lower()
    content = payload.get("content") or ""

    if not name:
        return jsonify({"message": "Informe o nome do script."}), 400
    if not content:
        return jsonify({"message": "O conteúdo do script está vazio."}), 400

    try:
        script = script_engine.save_script(
            plc_id=plc_id,
            name=name,
            language=language,
            content=content,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return (
        jsonify(
            {
                "id": script.id,
                "name": script.name,
                "language": script.language,
                "content": script.content,
                "updated_at": script.updated_at.isoformat() if script.updated_at else None,
            }
        ),
        201,
    )


@api_bp.route("/plcs/<int:plc_id>/scripts/<int:script_id>", methods=["DELETE"])
@login_required
def delete_plc_script(plc_id: int, script_id: int):
    script = script_engine.get_script(script_id)
    if script is None or script.plc_id != plc_id:
        return jsonify({"message": "Script não encontrado."}), 404

    script_engine.delete_script(script_id)
    return jsonify({"deleted": script_id}), 200
