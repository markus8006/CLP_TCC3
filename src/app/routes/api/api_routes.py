from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
# from src.utils import role_required

from src.repository.Data_repository import DataRepo
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Alarms_repository import AlarmRepo, AlarmDefinitionRepo

api_bp = Blueprint('apii', __name__)

@api_bp.route("/get/data/clp/<ip>", methods=["GET"])
@login_required
def get_data(ip):
    # busca o CLP
    clp = Plcrepo.first_by(ip_address=ip)
    if clp is None:
        return jsonify({"error": "CLP not found"}), 404

    # busca registros associados
    register = RegRepo.find_by(plc_id=clp.id)
    if not register:
        return jsonify({"error": "Register not found for CLP"}), 404

    # garante lista
    if not isinstance(register, list):
        register = [register]

    register = [r.id for r in register]

    # coleções agregadas
    data = []
    alarms_data = []
    defi_data = []

    for r in register:
        registros_data = DataRepo.find_by(register_id=r.id)
        registers_alarm = AlarmRepo().find_by(plc_id=clp.id, register_id=r.id)
        definitions_alarm = AlarmDefinitionRepo().find_by(plc_id=clp.id, register_id=r.id)

        # dados do registro
        if registros_data:
            if not isinstance(registros_data, list):
                registros_data = [registros_data]
            for d in registros_data:
                if hasattr(d, "__dict__"):
                    item = {k: v for k, v in d.__dict__.items() if not k.startswith("_")}
                else:
                    item = str(d)
                data.append(item)

        # alarmes do registro (agrega)
        if registers_alarm:
            if not isinstance(registers_alarm, list):
                registers_alarm = [registers_alarm]
            for alarm in registers_alarm:
                if hasattr(alarm, "__dict__"):
                    alarm_dict = {k: v for k, v in alarm.__dict__.items() if not k.startswith("_")}
                    alarms_data.append(alarm_dict)
                else:
                    alarms_data.append(str(alarm))

        # definições de alarme do registro (agrega)
        if definitions_alarm:
            if not isinstance(definitions_alarm, list):
                definitions_alarm = [definitions_alarm]
            for alarm_def in definitions_alarm:
                if hasattr(alarm_def, "__dict__"):
                    alarm_def_dict = {k: v for k, v in alarm_def.__dict__.items() if not k.startswith("_")}
                    defi_data.append(alarm_def_dict)
                else:
                    defi_data.append(str(alarm_def))

    mensagem = {
        "clp_id": clp.id,
        "register": register_ids,
        "data": data,
        "alarms": alarms_data,
        "definitions_alarms": defi_data
    }

    return jsonify(mensagem), 200
