from flask import Blueprint, render_template
from flask_login import current_user
from src.repository.PLC_repository import Plcrepo

main = Blueprint('main', __name__, template_folder=)


def clps() -> dict: 
    clps = Plcrepo.list_all()
    plc_dict = {
    f"plc{i+1}": {"nome": plc.name, "ip_address": plc.ip_address}
    for i, plc in enumerate(clps)
    }
    return plc_dict



@main.route('/', methods=['GET', 'POST'])
def index():
    print(clps())
    return render_template("layouts/index.html", clps=clps())