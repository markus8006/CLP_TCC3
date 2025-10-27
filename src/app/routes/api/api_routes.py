from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy.orm import selectinload
from src.app.extensions import db
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Data import DataLog
from src.models.Alarms import Alarm, AlarmDefinition
from src.repository.PLC_repository import Plcrepo
from src.utils.tags import normalize_tag

api_bp = Blueprint("apii", __name__)

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
