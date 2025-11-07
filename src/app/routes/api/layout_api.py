"""Factory layout API endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.repository.FactoryLayout_repository import FactoryLayoutRepository
from src.utils.role.roles import role_required

from .common import (
    plc_status,
    register_status,
    status_label,
    utc_now,
    vlan_identifier,
    vlan_label,
    vlan_value_from_key,
)


def build_layout_payload() -> dict:
    layout_record = FactoryLayoutRepository.get_or_create_default()
    layout_schema = layout_record.layout_schema or {}
    nodes = list(layout_schema.get("nodes", []))
    connections = list(layout_schema.get("connections", []))

    node_by_id = {
        node.get("id"): node for node in nodes if isinstance(node, dict) and node.get("id")
    }

    def ensure_position(node: dict, fallback_index: int) -> None:
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

    registers_position_tracker: dict[int, int] = {}
    fallback_counter = len(node_by_id)
    connection_set = {
        (conn.get("source"), conn.get("target"))
        for conn in connections
        if isinstance(conn, dict)
    }

    vlan_status_counts: dict[str, dict[str, int]] = {}
    vlan_summary_data: dict[str, dict[str, object]] = {}

    for plc in plcs:
        vlan_key = vlan_identifier(plc.vlan_id)
        vlan_node = node_by_id.get(vlan_key)
        if vlan_node is None:
            vlan_node = {"id": vlan_key, "type": "vlan"}
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
                "label": vlan_label(plc.vlan_id),
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

        status = plc_status(plc, alarm_by_plc)
        location_label = plc.organization.name if plc.organization else None

        plc_node.update(
            {
                "label": plc.name or f"PLC {plc.id}",
                "meta_line": f"{plc.ip_address} · VLAN {plc.vlan_id or '-'}",
                "location_label": location_label,
                "status": status,
                "status_label": status_label(status),
                "metadata": {
                    "plc_id": plc.id,
                    "ip_address": plc.ip_address,
                    "vlan_id": plc.vlan_id,
                    "location": location_label,
                    "location_label": location_label,
                },
            }
        )

        vlan_counts = vlan_status_counts.setdefault(
            vlan_key, {"online": 0, "offline": 0, "alarm": 0, "inactive": 0}
        )
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

            reg_status = register_status(register, alarm_by_register)
            register_node.update(
                {
                    "label": register.name,
                    "meta_line": register.tag or register.address,
                    "status": reg_status,
                    "status_label": status_label(reg_status),
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
        vlan_node["status_label"] = status_label(status)
        vlan_node.setdefault("metadata", {})["plc_totals"] = counts
        vlan_summary_data[vlan_key] = {"status": status, "counts": counts.copy()}

    layout_payload = {
        "nodes": nodes,
        "connections": connections,
    }

    vlan_summary = {}
    for key, summary in vlan_summary_data.items():
        vlan_value = vlan_value_from_key(key)
        label = vlan_label(vlan_value)
        metadata = node_by_id.get(key, {}).get("metadata", {})
        vlan_summary[label] = {
            "status": summary["status"],
            "status_label": status_label(summary["status"]),
            "plc_count": sum(summary["counts"].values()),
            "plcs": metadata.get("plcs", []),
        }

    return {
        "layout": layout_payload,
        "vlan_summary": vlan_summary,
        "generated_at": utc_now().isoformat(),
    }


layout_api_bp = Blueprint("api_layout", __name__)


@layout_api_bp.route("", methods=["GET"])
@login_required
def dashboard_layout():
    return jsonify(build_layout_payload())


@layout_api_bp.route("", methods=["PUT"])
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

    return jsonify(build_layout_payload())


__all__ = ["layout_api_bp", "build_layout_payload"]
