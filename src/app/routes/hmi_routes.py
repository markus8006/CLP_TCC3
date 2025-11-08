"""Routes dedicated to the alarm monitoring interface."""

from flask import Blueprint, render_template
from flask_login import login_required


hmi_bp = Blueprint("hmi", __name__)


@hmi_bp.route("/", methods=["GET"])
@login_required
def hmi_home():
    """Render the streamlined alarm monitor."""

    return render_template("hmi/index.html")
