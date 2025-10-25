from flask import Blueprint, jsonify
from flask_login import login_required
from sqlalchemy.orm import selectinload
from src.app.extensions import db
from src.models.PLCs import PLC
from src.models.Registers import Register  # importe o modelo correto
from src.models.Data import DataLog

api_bp = Blueprint('apii', __name__)

@api_bp.route("/get/data/clp/<ip>", methods=["GET"])
@login_required
def get_data(ip):
    clp = (
        db.session.query(PLC)
        .options(
            selectinload(PLC.registers).selectinload(Register.datalogs),
            selectinload(PLC.registers).selectinload(Register.alarms),
            selectinload(PLC.registers).selectinload(Register.alarm_definitions)
        )
        .filter(PLC.ip_address == ip)
        .first()
    )
    
    if clp is None:
        return jsonify({"error": "CLP not found"}), 404

    registers_map = {r.id: r.name for r in clp.registers}
    data, alarms_data, defi_data = [], [], []

    for r in clp.registers:
        for d in r.datalogs[:30]:
            data.append({
                'id': d.id,
                'register_id': d.register_id,
                'timestamp': d.timestamp.isoformat() if d.timestamp else None,
                'value_float': d.value_float,
                'quality': d.quality,
            })
        for alarm in r.alarms:
            alarms_data.append({
                'id': alarm.id,
                'plc_id': alarm.plc_id,
                'register_id': alarm.register_id,
                'state': alarm.state,
                'priority': alarm.priority,
                'message': alarm.message,
                
            })
        for alarm_def in r.alarm_definitions:
            defi_data.append({
                'id': alarm_def.id,
                'register_id': r.id,
                'name': alarm_def.name,
                'condition_type': alarm_def.condition_type,
                'threshold_low': alarm_def.threshold_low,
                'threshold_high': alarm_def.threshold_high,
                'setpoint' : alarm_def.setpoint
            })

    return jsonify({
        "clp_id": clp.id,
        "registers": registers_map,
        "data": data,
        "alarms": alarms_data,
        "definitions_alarms": defi_data
    }), 200
