"""PLC and register related API endpoints."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, make_response, request
from flask_login import login_required
from sqlalchemy.orm import selectinload

from src.app.extensions import db
from src.models.Alarms import Alarm
from src.models.Data import DataLog
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.repository.PLC_repository import Plcrepo
from src.runtime.script_engine import ScriptEngine
from src.services.address_mapping import AddressMappingEngine
from src.services.register_import_service import RegisterImportExportService
from src.services.tag_discovery_service import discover_tags as discover_tags_async
from src.services.tag_simulation_service import get_simulated_tags
from src.utils.tags import normalize_tag

from .common import (
    await_sync,
    build_discovery_params,
    extract_address,
    extract_label,
    stringify,
)

plc_api_bp = Blueprint("api_plc", __name__)

register_service = RegisterImportExportService()
script_engine = ScriptEngine()


@plc_api_bp.route("/tag-discovery/<protocol>", methods=["POST"])
@login_required
def api_tag_discovery(protocol: str):
    params = request.get_json(silent=True) or {}
    try:
        tags = await_sync(discover_tags_async(protocol, params))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:  # pragma: no cover - depends on external libs
        return jsonify({"message": str(exc)}), 500

    return jsonify({"tags": tags})


@plc_api_bp.route("/tag-discovery/<protocol>/simulate", methods=["GET"])
@login_required
def api_tag_discovery_simulate(protocol: str):
    try:
        tags = get_simulated_tags(protocol)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 404

    return jsonify({"tags": tags})


@plc_api_bp.route("/get/data/clp/<ip>", methods=["GET"])
@login_required
def get_data_optimized(ip: str):
    vlan_id = request.args.get("vlan", type=int)
    query = (
        db.session.query(PLC)
        .options(
            selectinload(PLC.registers).selectinload(Register.datalogs),
            selectinload(PLC.registers).selectinload(Register.alarms),
            selectinload(PLC.registers).selectinload(Register.alarm_definitions),
        )
        .filter(PLC.ip_address == ip, PLC.is_active.is_(True))
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

        sorted_logs = sorted(
            register.datalogs,
            key=lambda d: d.timestamp or 0,
            reverse=True,
        )[:30]
        result["data"].extend(
            [
                {
                    "id": d.id,
                    "register_id": d.register_id,
                    "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                    "value_float": d.value_float,
                    "quality": d.quality,
                }
                for d in sorted_logs
            ]
        )

        result["alarms"].extend(
            [
                {
                    "id": a.id,
                    "plc_id": a.plc_id,
                    "register_id": a.register_id,
                    "state": a.state,
                    "priority": a.priority,
                    "message": a.message,
                }
                for a in register.alarms
                if a.state == "ACTIVE"
            ]
        )

        result["definitions_alarms"].extend(
            [
                {
                    "id": ad.id,
                    "register_id": register.id,
                    "name": ad.name,
                    "condition_type": ad.condition_type,
                    "threshold_low": ad.threshold_low,
                    "threshold_high": ad.threshold_high,
                    "setpoint": ad.setpoint,
                }
                for ad in register.alarm_definitions
                if ad.is_active
            ]
        )

    return jsonify(result), 200


@plc_api_bp.route("/clps/<ip>/tags/<tag>", methods=["DELETE"])
@login_required
def remove_tag(ip: str, tag: str):
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


@plc_api_bp.route("/plcs/<int:plc_id>/discover", methods=["POST"])
@login_required
def discover_and_store(plc_id: int):
    plc = db.session.get(PLC, plc_id)
    if plc is None:
        return jsonify({"message": "CLP não encontrado."}), 404

    if not plc.protocol:
        return jsonify({"message": "O protocolo do CLP não está configurado."}), 400

    params = build_discovery_params(plc)

    try:
        discovered = await_sync(discover_tags_async(plc.protocol, params))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:  # pragma: no cover - depends on external libs
        return jsonify({"message": str(exc)}), 500

    engine = AddressMappingEngine()
    existing = {register.address: register for register in Register.query.filter_by(plc_id=plc.id).all()}

    created = 0
    updated = 0
    processed_ids: list[int] = []
    discovered_slugs = set()

    try:
        for entry in discovered:
            address = extract_address(entry)
            if not address:
                continue

            address_key = str(address).strip()
            if not address_key:
                continue

            label = extract_label(entry, address_key)
            tag_source = label or address_key
            slug = normalize_tag(tag_source) if tag_source else None

            data_type = (
                stringify(entry.get("data_type"))
                or stringify(entry.get("type"))
                or "desconhecido"
            )
            unit = stringify(entry.get("unit")) or stringify(entry.get("units"))
            description = stringify(entry.get("description")) or stringify(entry.get("comment"))
            register_type = stringify(entry.get("register_type")) or "analogue"
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
    except Exception:
        db.session.rollback()
        raise

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


@plc_api_bp.route("/registers/import", methods=["POST"])
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
    except Exception as exc:  # pragma: no cover - external parsing
        return jsonify({"message": f"Não foi possível ler o ficheiro: {exc}"}), 400

    created, errors = register_service.import_dataframe(frame, plc=plc, protocol=plc.protocol)
    return jsonify({"created": created, "errors": errors}), 201


@plc_api_bp.route("/registers/export", methods=["GET"])
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


@plc_api_bp.route("/registers/export/all", methods=["GET"])
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


@plc_api_bp.route("/plcs/<int:plc_id>/scripts", methods=["GET"])
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


@plc_api_bp.route("/plcs/<int:plc_id>/scripts", methods=["POST"])
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


@plc_api_bp.route("/plcs/<int:plc_id>/scripts/<int:script_id>", methods=["DELETE"])
@login_required
def delete_plc_script(plc_id: int, script_id: int):
    script = script_engine.get_script(script_id)
    if script is None or script.plc_id != plc_id:
        return jsonify({"message": "Script não encontrado."}), 404

    script_engine.delete_script(script_id)
    return jsonify({"deleted": script_id}), 200


__all__ = ["plc_api_bp"]
