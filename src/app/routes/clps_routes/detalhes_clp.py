from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from src.repository.PLC_repository import Plcrepo
from src.utils import role_required
from src.services.security.industrial_security import assess_plc_security


clp_bp = Blueprint("clp_bp", __name__)


@clp_bp.route("/clp/<ip>", methods=["GET"])
@login_required
def clp(ip):
    vlan_id = request.args.get("vlan", type=int)
    plc = Plcrepo.get_by_ip(ip, vlan_id)
    if plc is None:
        abort(404)

    security_report = assess_plc_security(plc)
    return render_template(
        "clp/detalhes.html",
        clp=plc,
        security_report=security_report,
        tags=plc.tags_as_list(),
        vlan_id=vlan_id,
    )
