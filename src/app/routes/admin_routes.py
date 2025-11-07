from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from src.app import db
from src.models.Users import User, UserRole
from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Alarms import AlarmDefinition
from src.repository.PLC_repository import Plcrepo
from src.repository.Registers_repository import RegRepo
from src.repository.Alarms_repository import AlarmDefinitionRepo
from src.services.polling_runtime import trigger_polling_refresh
from src.services.settings_service import get_polling_enabled, set_polling_enabled
from src.utils.role.roles import role_required
from src.utils.constants.constants import ROLES_HIERARCHY
from src.utils.tags import parse_tags

from .admin_forms import (
    ROLE_LABELS,
    AlarmDefinitionForm,
    PLCForm,
    PollingControlForm,
    RegisterCreationForm,
    UserCreationForm,
    UserUpdateForm,
)

AlarmDefRepo = AlarmDefinitionRepo()

admin_bp = Blueprint("admin", __name__)


def admin_role_required(min_role):
    """Decorator configurado para respostas HTML."""

    return role_required(min_role, format="html")


def _plc_label(plc: PLC) -> str:
    """Return a concise label with name, IP and optional VLAN."""

    vlan_info = f" VLAN {plc.vlan_id}" if plc.vlan_id else ""
    return f"{plc.name} ({plc.ip_address}{vlan_info})"


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.ADMIN)
def manage_users():
    create_form = UserCreationForm()

    if create_form.submit.data and create_form.validate_on_submit():
        new_user = User(
            username=create_form.username.data,
            email=create_form.email.data,
            role=UserRole(create_form.role.data),
        )
        new_user.set_password(create_form.password.data)
        db.session.add(new_user)
        try:
            db.session.commit()
            flash("Utilizador criado com sucesso!", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Nome de utilizador ou email já registado.", "warning")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao criar utilizador: {exc}", "danger")
        return redirect(url_for("admin.manage_users"))

    users = User.query.order_by(User.created_at.desc()).all()
    update_forms = {
        user.id: UserUpdateForm(
            prefix=f"user-{user.id}",
            data={"role": user.role.value, "is_active": user.is_active},
        )
        for user in users
    }

    ordering = {role.value: idx for idx, role in enumerate(UserRole.ordered_roles())}
    role_definitions = []
    for role_key, data in ROLES_HIERARCHY.items():
        enum_member = getattr(UserRole, role_key, None)
        if not enum_member:
            continue
        role_definitions.append(
            {
                "name": enum_member.value,
                "label": ROLE_LABELS.get(enum_member, role_key.title()),
                "description": data.get("description", ""),
                "permissions": data.get("permissions", []),
            }
        )
    role_definitions.sort(key=lambda item: ordering.get(item["name"], 0))

    return render_template(
        "admin/manage_users.html",
        users=users,
        create_form=create_form,
        update_forms=update_forms,
        role_definitions=role_definitions,
    )


@admin_bp.route("/users/<int:user_id>", methods=["POST"])
@login_required
@admin_role_required(UserRole.ADMIN)
def update_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = UserUpdateForm(prefix=f"user-{user.id}", formdata=request.form)

    if form.validate_on_submit():
        try:
            user.role = UserRole(form.role.data)
            user.is_active = form.is_active.data
            db.session.commit()
            flash("Utilizador actualizado!", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao actualizar utilizador: {exc}", "danger")
    else:
        flash("Não foi possível actualizar o utilizador.", "danger")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_role_required(UserRole.ADMIN)
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Não é possível remover o utilizador autenticado actualmente.", "warning")
        return redirect(url_for("admin.manage_users"))

    try:
        db.session.delete(user)
        db.session.commit()
        flash("Utilizador removido com sucesso.", "info")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao remover utilizador: {exc}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/clps", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.MODERATOR)
def manage_clps():
    form = PLCForm()

    if request.method == "GET":
        form.tags.data = ""

    if form.validate_on_submit():
        actor = current_user.username if current_user.is_authenticated else None
        plc = PLC(
            name=form.name.data,
            description=form.description.data,
            ip_address=form.ip_address.data,
            protocol=form.protocol.data,
            port=form.port.data,
            vlan_id=form.vlan_id.data,
            subnet_mask=form.subnet_mask.data,
            gateway=form.gateway.data,
            unit_id=form.unit_id.data,
            manufacturer=form.manufacturer.data,
            model=form.model.data,
            firmware_version=form.firmware_version.data,
            is_active=form.is_active.data,
        )
        plc.set_tags(parse_tags(form.tags.data))
        if plc.is_active:
            plc.mark_active(actor=actor, source="admin_ui")
        else:
            plc.mark_inactive(actor=actor, source="admin_ui")
        try:
            Plcrepo.add(plc, commit=False)
            db.session.commit()
            flash("CLP criado com sucesso!", "success")
            trigger_polling_refresh(current_app)
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um CLP com este IP ou nome.", "warning")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao criar CLP: {exc}", "danger")
        return redirect(url_for("admin.manage_clps"))

    plcs = Plcrepo.list_all()

    return render_template(
        "clp/manage.html",
        form=form,
        plcs=plcs,
        polling_enabled=get_polling_enabled(),
    )


@admin_bp.route("/clps/<int:plc_id>", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.MODERATOR)
def edit_clp(plc_id: int):
    plc = PLC.query.get_or_404(plc_id)
    form = PLCForm(obj=plc)
    if request.method == "GET":
        form.tags.data = ", ".join(plc.tags_as_list())

    if form.validate_on_submit():
        previous_state = plc.is_active
        actor = current_user.username if current_user.is_authenticated else None
        try:
            form.populate_obj(plc)
            plc.set_tags(parse_tags(form.tags.data))
            if plc.is_active and not previous_state:
                plc.mark_active(actor=actor, source="admin_ui")
            elif previous_state and not plc.is_active:
                plc.mark_inactive(actor=actor, source="admin_ui")
            db.session.commit()
            flash("CLP actualizado com sucesso!", "success")
            trigger_polling_refresh(current_app)
        except IntegrityError:
            db.session.rollback()
            flash("Conflito de IP ou nome ao actualizar o CLP.", "warning")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao actualizar CLP: {exc}", "danger")
        return redirect(url_for("admin.manage_clps"))

    return render_template("clp/edit.html", form=form, plc=plc)


@admin_bp.route("/clps/<int:plc_id>/delete", methods=["POST"])
@login_required
@admin_role_required(UserRole.MODERATOR)
def delete_clp(plc_id: int):
    plc = PLC.query.get_or_404(plc_id)

    try:
        db.session.delete(plc)
        db.session.commit()
        flash("CLP removido com sucesso!", "success")
        trigger_polling_refresh(current_app)
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao remover CLP: {exc}", "danger")

    return redirect(url_for("admin.manage_clps"))


@admin_bp.route("/registers", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.MODERATOR)
def manage_registers():
    form = RegisterCreationForm()
    plcs = PLC.query.order_by(PLC.name.asc()).all()
    form.plc_id.choices = [(plc.id, _plc_label(plc)) for plc in plcs]

    if form.validate_on_submit():
        register = Register(
            plc_id=form.plc_id.data,
            name=form.name.data,
            description=form.description.data,
            address=form.address.data,
            register_type=form.register_type.data,
            data_type=form.data_type.data,
            length=form.length.data or 1,
            unit=form.unit.data,
            scale_factor=form.scale_factor.data if form.scale_factor.data is not None else 1.0,
            offset=form.offset.data if form.offset.data is not None else 0.0,
            tag=form.tag.data,
        )
        try:
            RegRepo.add(register, commit=False)
            db.session.commit()
            flash("Registrador criado com sucesso!", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um registrador com este endereço para o CLP seleccionado.", "warning")
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao criar registrador: {exc}", "danger")
        return redirect(url_for("admin.manage_registers"))

    registers = RegRepo.list_all()

    return render_template(
        "registers/manage.html",
        form=form,
        registers=registers,
    )


@admin_bp.route("/registers/<int:register_id>/delete", methods=["POST"])
@login_required
@admin_role_required(UserRole.MODERATOR)
def delete_register(register_id: int):
    register = Register.query.get_or_404(register_id)

    try:
        db.session.delete(register)
        db.session.commit()
        flash("Registrador removido com sucesso!", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao remover registrador: {exc}", "danger")

    return redirect(url_for("admin.manage_registers"))


@admin_bp.route("/polling/control", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.GERENTE)
def manage_polling_control():
    form = PollingControlForm()
    persisted_enabled = get_polling_enabled()
    runtime = current_app.extensions.get("polling_runtime")
    runtime_enabled = runtime.is_enabled() if runtime else persisted_enabled

    if request.method == "GET":
        form.enabled.data = persisted_enabled

    if form.validate_on_submit():
        set_polling_enabled(
            form.enabled.data,
            actor=current_user.username if current_user.is_authenticated else None,
        )
        flash("Estado do polling actualizado.", "success")
        return redirect(url_for("admin.manage_polling_control"))

    return render_template(
        "admin/polling_control.html",
        form=form,
        db_enabled=persisted_enabled,
        runtime_enabled=runtime_enabled,
    )


@admin_bp.route("/alarms/definitions", methods=["GET", "POST"])
@login_required
@admin_role_required(UserRole.ALARM_DEFINITION)
def manage_alarm_definitions():
    form = AlarmDefinitionForm()

    plcs = PLC.query.order_by(PLC.name.asc()).all()
    form.plc_id.choices = [(plc.id, _plc_label(plc)) for plc in plcs]

    registers_by_plc = {}
    default_register_choices = [(0, "Sem registrador associado")]
    for plc in plcs:
        registers = (
            Register.query.filter_by(plc_id=plc.id)
            .order_by(Register.name.asc())
            .all()
        )
        formatted_registers = [
            {"id": register.id, "label": f"{register.name} ({register.address})"}
            for register in registers
        ]
        registers_by_plc[plc.id] = formatted_registers
        default_register_choices.extend(
            [
                (
                    register["id"],
                    f"{register['label']} — {_plc_label(plc)}",
                )
                for register in formatted_registers
            ]
        )

    form.register_id.choices = (
        default_register_choices or [(0, "Sem registradores disponíveis")]
    )

    if form.validate_on_submit():
        register_id = form.register_id.data if form.register_id.data != 0 else None
        definition = AlarmDefinition(
            plc_id=form.plc_id.data,
            register_id=register_id,
            name=form.name.data,
            description=form.description.data,
            condition_type=form.condition_type.data,
            setpoint=form.setpoint.data,
            threshold_low=form.threshold_low.data,
            threshold_high=form.threshold_high.data,
            deadband=form.deadband.data if form.deadband.data is not None else 0.0,
            priority=form.priority.data,
            severity=form.severity.data if form.severity.data is not None else 3,
            is_active=form.is_active.data,
            auto_acknowledge=form.auto_acknowledge.data,
            email_enabled=form.email_enabled.data,
            email_min_role=UserRole(form.email_min_role.data),
        )

        try:
            AlarmDefRepo.add(definition, commit=False)
            db.session.commit()
            flash("Definição de alarme criada com sucesso!", "success")
            return redirect(url_for("admin.manage_alarm_definitions"))
        except IntegrityError:
            db.session.rollback()
            flash(
                "Já existe uma definição semelhante para este registrador.",
                "warning",
            )
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao criar definição de alarme: {exc}", "danger")

    definitions = AlarmDefRepo.list_all()

    return render_template(
        "alarms/manage.html",
        form=form,
        definitions=definitions,
        registers_by_plc=registers_by_plc,
        role_labels=ROLE_LABELS,
    )


@admin_bp.route("/alarms/definitions/<int:definition_id>/delete", methods=["POST"])
@login_required
@admin_role_required(UserRole.ALARM_DEFINITION)
def delete_alarm_definition(definition_id: int):
    definition = AlarmDefinition.query.get_or_404(definition_id)

    try:
        db.session.delete(definition)
        db.session.commit()
        flash("Definição de alarme removida com sucesso!", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao remover definição de alarme: {exc}", "danger")

    return redirect(url_for("admin.manage_alarm_definitions"))
