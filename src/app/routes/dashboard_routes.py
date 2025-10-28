"""Routes responsible for the analytical dashboard and layout designer."""
from flask import Blueprint, render_template
from flask_login import current_user, login_required


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/", methods=["GET"])
@login_required
def dashboard_home():
    """Renderiza a área de dashboard com gráficos e o designer da fábrica."""

    return render_template(
        "dashboard/index.html",
        is_admin=current_user.has_permission("admin"),
    )
