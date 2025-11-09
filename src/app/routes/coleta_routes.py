"""Rotas relacionadas à gestão da coleta de IPs."""

from __future__ import annotations

from typing import Optional

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import BooleanField, SubmitField

from src.models.Users import UserRole
from src.services import discovery_service
from src.utils import role_required
from src.utils.logs import logger


class DiscoveryControlForm(FlaskForm):
    enabled = BooleanField("Ativar descoberta de rede")
    submit = SubmitField("Atualizar estado")
    run_scan = SubmitField("Executar varredura agora")


coleta_bp = Blueprint("coleta", __name__)


@coleta_bp.route("/", methods=["GET", "POST"])
@login_required
@role_required(UserRole.ENGINEER)
def control():
    form = DiscoveryControlForm()

    persisted_enabled = discovery_service.is_discovery_enabled()
    last_run = discovery_service.get_last_run_time()
    summary = discovery_service.load_discovery_summary()
    total_devices = len(summary)
    industrial_count = discovery_service.count_industrial_devices(summary)
    has_privileges = discovery_service.has_network_privileges()

    if request.method == "GET":
        form.enabled.data = persisted_enabled

    if form.validate_on_submit():
        actor = current_user.username if current_user.is_authenticated else None

        if form.submit.data:
            discovery_service.set_discovery_enabled(
                form.enabled.data,
                actor=actor,
            )
            flash("Estado da descoberta atualizado.", "success")
            return redirect(url_for("coleta.control"))

        if form.run_scan.data:
            if not has_privileges:
                flash(
                    "Permissões insuficientes para executar a descoberta. Execute o serviço como administrador.",
                    "danger",
                )
            elif not discovery_service.is_discovery_enabled():
                flash(
                    "A descoberta está desativada. Atualize o estado para activar a coleta antes de executar uma varredura.",
                    "warning",
                )
            else:
                try:
                    devices = discovery_service.execute_discovery(actor=actor)
                    flash(
                        f"Varredura concluída: {len(devices)} dispositivos identificados.",
                        "success",
                    )
                    return redirect(url_for("coleta.control"))
                except Exception as exc:  # pragma: no cover - defensivo
                    logger.exception("Erro ao executar varredura de rede")
                    flash(f"Erro ao executar varredura: {exc}", "danger")

    last_run_display: Optional[str] = None
    if last_run:
        last_run_display = last_run.astimezone().strftime("%d/%m/%Y %H:%M:%S %Z")

    summary_preview = summary[:20]

    return render_template(
        "coleta/control.html",
        form=form,
        persisted_enabled=persisted_enabled,
        total_devices=total_devices,
        industrial_count=industrial_count,
        last_run_display=last_run_display,
        summary_preview=summary_preview,
        has_privileges=has_privileges,
    )
