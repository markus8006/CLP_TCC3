from flask import Blueprint, render_template
from flask_login import current_user, login_required
from src.repository.PLC_repository import Plcrepo
from src.utils import role_required


clp_bp = Blueprint("clp_bp", __name__)


@clp_bp.route("/clp/<ip>", methods=["GET"])
def clp(ip):
    CLP = Plcrepo.first_by(ip_address = ip).__dict__
    print(CLP)
    return render_template("teste")
