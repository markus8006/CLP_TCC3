"""Routes dedicated to the interactive HMI/SCADA interface."""

from flask import Blueprint, render_template
from flask_login import login_required, current_user


hmi_bp = Blueprint("hmi", __name__)


@hmi_bp.route("/", methods=["GET"])
@login_required
def hmi_home():
    """Render the Synoptic HMI bringing process overview and controls."""

    return render_template(
        "hmi/index.html",
        can_control=current_user.has_permission("operator"),
        is_admin=current_user.has_permission("admin"),
    )
