from flask import Blueprint
from flask_login import current_user, login_required
from src.repository.PLC_repository import Plcrepo
from src.utils import role_required



api_bp = Blueprint("api_bp", __name__)


@api_bp.route("get/polling/data/<ip>", methods=["GET"])
def get_data(ip):
    pass
