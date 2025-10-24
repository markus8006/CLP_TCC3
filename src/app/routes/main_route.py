from flask import Blueprint, render_template
from flask_login import current_user, login_required
from src.repository.PLC_repository import Plcrepo
from src.utils import role_required

main = Blueprint('main', __name__)


def clps() -> dict: 
    clps = Plcrepo.list_all()
    plc_dict = {
    f"plc{i+1}": {"nome": plc.name, "ip_address": plc.ip_address}
    for i, plc in enumerate(clps)
    }
    return plc_dict




# @role_required("user")
@login_required
@main.route('/', methods=['GET', 'POST'])
def index():
    print(clps())
    return render_template("index/index.html", clps=clps())