import asyncio
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, request
from flask_login import current_user, login_required
from sqlalchemy import case, func
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm, AlarmDefinition
from src.models.Data import DataLog
from src.models.ManualControl import ManualCommand
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.repository.FactoryLayout_repository import FactoryLayoutRepository
from src.repository.PLC_repository import Plcrepo
from src.runtime.script_engine import ScriptEngine
from src.services.register_import_service import RegisterImportExportService
from src.services.address_mapping import AddressMappingEngine
from src.services.tag_discovery_service import discover_tags as discover_tags_async
from src.services.tag_simulation_service import get_simulated_tags
from src.services.manual_control_service import ManualControlService
from src.services.historian_sync_service import HistorianSyncService
from src.utils.role.roles import role_required
from src.utils.tags import normalize_tag

api_bp = Blueprint("apii", __name__)


def api_role_required(min_role):
    """Decorator configurado para respostas JSON."""

    return role_required(min_role, format="json")

STATUS_LABELS = {
    "online": "Online",
    "offline": "Offline",
    "alarm": "Em alarme",
    "inactive": "Inativo",
}

register_service = RegisterImportExportService()
script_engine = ScriptEngine()
manual_control_service = ManualControlService()
historian_sync_service = HistorianSyncService()


def _stringify(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value if item is not None and str(item).strip()]
        return " / ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def _extract_address(entry: dict) -> str | None:
    direct = _stringify(entry.get("address")) or _stringify(entry.get("node_id"))
    if direct:
        return direct

    path = _stringify(entry.get("path")) or _stringify(entry.get("display_path"))
    if path:
        return path

    group = entry.get("group")
    variation = entry.get("variation")
    index = entry.get("index")
    if group is not None and variation is not None and index is not None:
        return f"g{group}v{variation}/{index}"

    if index is not None:
        subindex = entry.get("subindex")
        if subindex is not None:
            return f"{index}/{subindex}"
        return str(index)

    tag_name = _stringify(entry.get("tag_name"))
    if tag_name:
        return tag_name

    return None


def _extract_label(entry: dict, fallback: str | None = None) -> str | None:
    label = (
        _stringify(entry.get("tag_name"))
        or _stringify(entry.get("name"))
        or _stringify(entry.get("label"))
        or _stringify(entry.get("display_path"))
    )
    if label:
        return label

    path = _stringify(entry.get("path"))
    if path:
        return path

    node_id = _stringify(entry.get("node_id"))
    if node_id:
        return node_id

    return fallback


def _build_discovery_params(plc: PLC) -> dict:
    params = {
        "ip": plc.ip_address,
        "host": plc.ip_address,
        "address": plc.ip_address,
        "port": plc.port,
    }

    protocol = (plc.protocol or "").lower()
    if protocol in {"modbus", "modbus-tcp", "modbus_rtu", "modbus-rtu"}:
        if plc.unit_id is not None:
            params["unit_id"] = plc.unit_id
            params["slave"] = plc.unit_id

    if protocol in {"s7", "siemens"} and plc.rack_slot:
        rack_slot = str(plc.rack_slot).replace(",", ".").split(".")
        try:
            params["rack"] = int(rack_slot[0])
        except (ValueError, IndexError):
            pass
        try:
            params["slot"] = int(rack_slot[1])
        except (ValueError, IndexError):
            pass

    return {key: value for key, value in params.items() if value not in (None, "")}


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


@api_bp.route("/tag-discovery/<protocol>/simulate", methods=["GET"])
@login_required
def api_tag_discovery_simulate(protocol: str):
    try:
        tags = get_simulated_tags(protocol)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 404

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
        "definitions_alarms": [],
    }

    for register in filter(lambda r: r.is_active, clp.registers):
        result["registers"][str(register.id)] = {
            "name": register.name,
            "tag": register.tag,
            "tag_name": register.tag_name,
            "address": register.address,
        }

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
@api_role_required("admin")
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


@api_bp.route("/plcs/<int:plc_id>/discover", methods=["POST"])
@login_required
def discover_and_store(plc_id: int):
    plc = db.session.get(PLC, plc_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    if not plc.protocol:
        return jsonify({"message": "O protocolo do CLP não está configurado."}), 400

    params = _build_discovery_params(plc)

    try:
        discovered = _await(discover_tags_async(plc.protocol, params))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:  # pragma: no cover - depende de libs externas
        return jsonify({"message": str(exc)}), 500

    engine = AddressMappingEngine()
    existing = {
        register.address: register
        for register in Register.query.filter_by(plc_id=plc.id).all()
    }

    created = 0
    updated = 0
    processed_ids = []
    discovered_slugs = set()

    try:
        for entry in discovered:
            address = _extract_address(entry)
            if not address:
                continue

            address_key = str(address).strip()
            if not address_key:
                continue

            label = _extract_label(entry, address_key)
            tag_source = label or address_key
            slug = normalize_tag(tag_source) if tag_source else None

            data_type = (
                _stringify(entry.get("data_type"))
                or _stringify(entry.get("type"))
                or "desconhecido"
            )
            unit = _stringify(entry.get("unit")) or _stringify(entry.get("units"))
            description = _stringify(entry.get("description")) or _stringify(entry.get("comment"))
            register_type = _stringify(entry.get("register_type")) or "analogue"
            length = entry.get("length")

            try:
                normalized_address = engine.normalize(plc.protocol, address_key)
            except ValueError:
                normalized_address = {"raw": address_key}

            register = existing.get(address_key)
            if register:
                register.name = label or register.name or address_key
                register.tag = slug or register.tag
                register.tag_name = label or register.tag_name
                register.data_type = data_type or register.data_type
                register.unit = unit or register.unit
                register.description = description or register.description
                register.protocol = plc.protocol
                register.register_type = register_type or register.register_type
                register.normalized_address = normalized_address
                if length is not None:
                    register.length = length
                updated += 1
            else:
                register = Register(
                    plc_id=plc.id,
                    name=label or address_key,
                    tag=slug,
                    tag_name=label or None,
                    address=address_key,
                    register_type=register_type or "analogue",
                    data_type=data_type or "desconhecido",
                    unit=unit,
                    description=description,
                    protocol=plc.protocol,
                    normalized_address=normalized_address,
                )
                if length is not None:
                    register.length = length
                db.session.add(register)
                db.session.flush()
                existing[address_key] = register
                created += 1

            if register.id not in processed_ids:
                processed_ids.append(register.id)

            if slug:
                discovered_slugs.add(slug)

        if discovered_slugs:
            combined = set(plc.tags_as_list())
            combined.update(discovered_slugs)
            Plcrepo.update_tags(plc, combined, commit=False)

        db.session.commit()
    except Exception as exc:  # pragma: no cover - commit/flush errors
        db.session.rollback()
        return jsonify({"message": f"Falha ao guardar os dados descobertos: {exc}"}), 500

    total_registers = Register.query.filter_by(plc_id=plc.id).count()
    message = (
        "Nenhuma tag encontrada para o protocolo configurado."
        if created == 0 and updated == 0
        else f"Sincronização concluída: {created} registradores criados e {updated} atualizados."
    )

    return jsonify(
        {
            "message": message,
            "tags": plc.tags_as_list(),
            "discovered": len(discovered),
            "registers_created": created,
            "registers_updated": updated,
            "registers_total": total_registers,
            "register_ids": processed_ids,
        }
    )


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


@api_bp.route("/registers/export/all", methods=["GET"])
@login_required
def export_all_registers():
    file_format = request.args.get("format", "csv").lower()
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    if file_format not in {"csv", "xlsx"}:
        file_format = "csv"

    query = (
        Register.query.options(selectinload(Register.plc))
        .join(PLC)
        .order_by(PLC.name, Register.name)
    )

    if not include_inactive:
        query = query.filter(Register.is_active.is_(True))

    registers = query.all()
    if not registers:
        return jsonify({"message": "Não há registradores cadastrados."}), 404

    frame = register_service.export_dataframe(registers, include_plc=True)
    data, mime = register_service.export_to_bytes(frame, file_format=file_format)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"registers_all_{timestamp}.{file_format}"

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


@api_bp.route("/hmi/overview", methods=["GET"])
@login_required
def hmi_overview():
    """Aggregates data for the synoptic HMI view and performance metrics."""

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
        area_key = _vlan_identifier(plc.vlan_id)
        area = areas.setdefault(
            area_key,
            {
                "id": area_key,
                "label": _vlan_label(plc.vlan_id),
                "plcs": [],
            },
        )

        registers_payload = []
        for register in sorted(plc.registers, key=lambda item: item.name.lower()):
            if not register.is_active:
                continue
            status = _register_status(register, alarm_by_register)
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
                "status": _plc_status(plc, alarm_by_plc),
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

    return jsonify(
        {
            "areas": list(areas.values()),
            "register_options": register_options,
            "report_metrics": report_metrics,
        }
    )


@api_bp.route("/hmi/alarms", methods=["GET"])
@login_required
def hmi_active_alarms():
    """Return active alarms with contextual information."""

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
                "triggered_at": alarm.triggered_at.isoformat()
                if alarm.triggered_at
                else None,
                "age_seconds": (
                    (now - alarm.triggered_at).total_seconds()
                    if alarm.triggered_at
                    else None
                ),
            }
        )

    return jsonify({"alarms": payload})


@api_bp.route("/hmi/manual-commands", methods=["GET"])
@login_required
def hmi_manual_history():
    """Return the most recent manual commands executed via the HMI."""

    commands = manual_control_service.recent_commands(limit=25)
    return jsonify({"commands": [command.as_dict() for command in commands]})


@api_bp.route("/hmi/manual-commands/pending", methods=["GET"])
@login_required
@role_required("engineer")
def hmi_manual_pending():
    """Expose commands awaiting approval for supervisory review."""

    commands = manual_control_service.pending_commands()
    return jsonify({"commands": [command.as_dict() for command in commands]})


@api_bp.route("/hmi/register/<int:register_id>/trend", methods=["GET"])
@login_required
def hmi_register_trend(register_id: int):
    """Return the last readings for the requested register."""

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


@api_bp.route("/hmi/register/<int:register_id>/manual", methods=["POST"])
@login_required
@api_role_required("operator")
def hmi_execute_manual_command(register_id: int):
    """Enqueue a manual command for supervisory approval."""

    payload = request.get_json(silent=True) or {}
    command_type = payload.get("command_type", "setpoint")

    value = payload.get("value")
    value_numeric = None
    if value is not None:
        try:
            value_numeric = float(value)
        except (TypeError, ValueError):
            return jsonify({"message": "Valor numérico inválido."}), 400

    note = payload.get("note")

    try:
        result = manual_control_service.execute_command(
            register_id=register_id,
            command_type=command_type,
            value=value_numeric,
            value_text=str(value) if value is not None else None,
            executed_by=current_user.username,
            note=note,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return jsonify(
        {
            "message": "Comando enviado para aprovação.",
            "command": result.command.as_dict(),
        }
    )


@api_bp.route("/interlock/manual-commands/<int:command_id>/approve", methods=["POST"])
@login_required
@role_required("engineer")
def interlock_approve_manual_command(command_id: int):
    """Approve a pending manual command."""

    payload = request.get_json(silent=True) or {}
    reviewer_note = payload.get("note")
    try:
        command = manual_control_service.approve_command(
            command_id,
            approved_by=current_user.username,
            reviewer_note=reviewer_note,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return jsonify({"command": command.as_dict()})


@api_bp.route("/interlock/manual-commands/<int:command_id>/reject", methods=["POST"])
@login_required
@role_required("engineer")
def interlock_reject_manual_command(command_id: int):
    """Reject a manual command request."""

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if not reason:
        return jsonify({"message": "Informe o motivo da rejeição."}), 400

    try:
        command = manual_control_service.reject_command(
            command_id,
            rejected_by=current_user.username,
            reason=reason,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return jsonify({"command": command.as_dict()})


@api_bp.route("/interlock/manual-commands/<int:command_id>/dispatch", methods=["POST"])
@login_required
@role_required("engineer")
def interlock_dispatch_manual_command(command_id: int):
    """Dispatch an approved manual command to the PLC writer layer."""

    payload = request.get_json(silent=True) or {}
    execution_note = payload.get("note")
    try:
        result = manual_control_service.dispatch_command(
            command_id,
            dispatcher=current_user.username,
            execution_note=execution_note,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    return jsonify(
        {
            "command": result.command.as_dict(),
            "datalog_id": result.datalog.id if result.datalog else None,
        }
    )


@api_bp.route("/historian/export", methods=["POST"])
@login_required
@api_role_required("admin")
def historian_export():
    """Generate a CSV snapshot of historian data for BI consumption."""

    payload = request.get_json(silent=True) or {}

    def _parse_dt(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            raise ValueError("Formato de data inválido. Use ISO 8601.")

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
