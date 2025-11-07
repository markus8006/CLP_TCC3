"""API blueprint aggregator."""
from __future__ import annotations

from flask import Blueprint

api_bp = Blueprint("apii", __name__)

from .dashboard_api import dashboard_api_bp
from .historian_api import historian_api_bp
from .layout_api import layout_api_bp
from .manual_control_api import manual_control_api_bp
from .plc_api import plc_api_bp

api_bp.register_blueprint(plc_api_bp)
api_bp.register_blueprint(dashboard_api_bp, url_prefix="/dashboard")
api_bp.register_blueprint(layout_api_bp, url_prefix="/dashboard/layout")
api_bp.register_blueprint(manual_control_api_bp, url_prefix="/hmi")
api_bp.register_blueprint(historian_api_bp, url_prefix="/historian")

__all__ = ["api_bp"]
