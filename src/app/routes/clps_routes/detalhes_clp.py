from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from src.app.routes.admin_forms import PLCForm, RegisterUpdateForm
from src.models.Users import UserRole
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
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
    registers = RegRepo.list_by_plc(plc.id)

    can_manage = current_user.is_authenticated and current_user.has_permission(UserRole.MODERATOR)
    clp_form = None
    register_forms = []

    if can_manage:
        clp_form = PLCForm(obj=plc)
        clp_form.tags.data = ", ".join(plc.tags_as_list())
        clp_form.submit.label.text = "Guardar alterações"

        plc_choices = []
        for option in Plcrepo.list_all():
            vlan_info = f" VLAN {option.vlan_id}" if option.vlan_id else ""
            plc_choices.append((option.id, f"{option.name} ({option.ip_address}{vlan_info})"))

        for register in registers:
            form = RegisterUpdateForm(obj=register, prefix=f"register-{register.id}")
            form.plc_id.choices = plc_choices
            form.plc_id.data = register.plc_id
            form.is_active.data = register.is_active
            form.log_enabled.data = register.log_enabled
            form.poll_rate.data = register.poll_rate
            form.submit.label.text = "Guardar alterações"
            register_forms.append((register, form))

    return render_template(
        "clp/detalhes.html",
        clp=plc,
        security_report=security_report,
        tags=plc.tags_as_list(),
        vlan_id=vlan_id,
        registers=registers,
        clp_form=clp_form,
        register_forms=register_forms,
        can_manage=can_manage,
    )
