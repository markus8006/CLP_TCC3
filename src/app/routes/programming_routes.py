from flask import Blueprint, render_template, request
from flask_login import login_required

from src.repository.PLC_repository import Plcrepo


programming_bp = Blueprint("programming", __name__)


@programming_bp.route("/", methods=["GET"])
@login_required
def hub():
    clps = Plcrepo.list_all()
    selected_plc = None
    selected_id = request.args.get("plc_id", type=int)

    if clps:
        if selected_id:
            selected_plc = next((plc for plc in clps if plc.id == selected_id), None)
        if selected_plc is None:
            selected_plc = clps[0]

    return render_template(
        "programming/index.html",
        clps=clps,
        selected_plc=selected_plc,
    )
