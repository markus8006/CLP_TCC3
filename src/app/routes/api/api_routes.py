from flask import Blueprint, jsonify
from flask_login import login_required

from src.repository.Data_repository import DataRepo
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Alarms_repository import AlarmRepo, AlarmDefinitionRepo

api_bp = Blueprint('apii', __name__)

def _to_dict(obj):
    """Converte um objeto simples em dict (ignora atributos privados)."""
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, dict):
        return obj
    return str(obj)

@api_bp.route("/get/data/clp/<ip>", methods=["GET"])
@login_required
def get_data(ip):
    # busca o CLP
    clp = Plcrepo.first_by(ip_address=ip)
    if clp is None:
        return jsonify({"error": "CLP not found"}), 404

    # busca registros associados (pode retornar um objeto ou uma lista)
    regs = RegRepo.find_by(plc_id=clp.id)
    if not regs:
        return jsonify({"error": "Register not found for CLP"}), 404

    # normaliza para lista de objetos
    if not isinstance(regs, list):
        regs = [regs]

    # cria map {id: nome} conforme pedido
    registers_map = {}
    for r in regs:
        # tenta diferentes campos comuns para nome, cai para string do id se nada existir
        name = getattr(r, "name", None) or getattr(r, "nome", None) or getattr(r, "tag", None) or str(getattr(r, "id", r))
        registers_map[getattr(r, "id", r)] = name

    # coleções agregadas
    data = []
    alarms_data = []
    defi_data = []

    # percorre os registros (aqui r é objeto, então usamos r.id)
    for r in regs:
        reg_id = getattr(r, "id", None)
        if reg_id is None:
            continue

        # dados do registro
        registros_data = DataRepo.find_by(register_id=reg_id)
        if registros_data:
            if not isinstance(registros_data, list):
                registros_data = [registros_data]
            for d in registros_data:
                data.append(_to_dict(d))

        # alarmes do registro
        registers_alarm = AlarmRepo().find_by(plc_id=clp.id, register_id=reg_id)
        if registers_alarm:
            if not isinstance(registers_alarm, list):
                registers_alarm = [registers_alarm]
            for alarm in registers_alarm:
                alarms_data.append(_to_dict(alarm))

        # definições de alarme do registro
        definitions_alarm = AlarmDefinitionRepo().find_by(plc_id=clp.id, register_id=reg_id)
        if definitions_alarm:
            if not isinstance(definitions_alarm, list):
                definitions_alarm = [definitions_alarm]
            for alarm_def in definitions_alarm:
                defi_data.append(_to_dict(alarm_def))

    mensagem = {
        "clp_id": clp.id,
        "registers": registers_map,       # formato solicitado: {id1: "nome1", id2: "nome2"}
        "data": data,
        "alarms": alarms_data,
        "definitions_alarms": defi_data
    }

    return jsonify(mensagem), 200
