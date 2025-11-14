#src/app/__init__.py


from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from src.app.extensions import csrf, db, login_manager, migrate
from src.app.settings import get_app_settings, load_settings, store_settings
from src.utils.logs import logger


def _ensure_directories(database_uri: str, *, log_dir: Path, backup_dir: Path) -> None:
    """Create filesystem paths required by the application when appropriate."""

    try:
        if database_uri.startswith("sqlite:///"):
            path = database_uri.replace("sqlite:///", "")
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        else:
            os.makedirs(log_dir, exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)
    except Exception:
        logger.exception("Erro ao criar diretórios (ignorando em ambiente de teste)")


def create_app(config_name: str | None = None) -> Flask:

    logger.process("Criando app")
    settings = load_settings(config_name)
    app = Flask(__name__)
    app.config.update(settings.as_flask_config())
    app.debug = settings.debug
    app.testing = settings.testing
    store_settings(app, settings)
    logger.info("app criado")

    logger.process("Configurando app")
    logger.warning(f"USANDO DB: {settings.database.url}")
    logger.info("app configurado")

    _ensure_directories(
        settings.database.url,
        log_dir=Path(settings.log_dir),
        backup_dir=Path(settings.backup_dir),
    )

    logger.process("Iniciando extensões")
    db.init_app(app)
    try:
        migrate.init_app(app, db)
    except Exception:
        logger.debug("Migrate init falhou (ok em testes).")
    login_manager.init_app(app)
    csrf.init_app(app)
    logger.info("extensões iniciadas")

    try:
        from src.models import (
            Alarm,
            AlarmDefinition,
            AuditLog,
            DataLog,
            FactoryLayout,
            ManualCommand,
            Organization,
            PLC,
            Register,
            SecurityEvent,
            User,
            UserRole,
        )

        with app.app_context():
            db.create_all()
            logger.info("Registrando blueprints")
            register_blueprints(app)
        logger.info("db criado")
    except Exception as exc:
        logger.debug(
            "Import models failed (ok for tests if models imported elsewhere). %s",
            exc,
        )

    return app


def register_blueprints(app: Flask) -> None:
    """Registra blueprints conforme o modo configurado."""

    from src.app.routes.api.api_routes import api_bp

    app.register_blueprint(api_bp, url_prefix='/api')
    logger.info("API registrada (sempre ativa)")

    settings = get_app_settings(app)
    app_mode = (settings.features.app_mode or "full").lower()
    if app_mode != "full":
        logger.info(
            "APP_MODE=%s — blueprints do frontend não serão registados.",
            app_mode,
        )
        return

    from src.app.routes.main_route import main as main_bp
    from src.app.routes.clps_routes.detalhes_clp import clp_bp
    from src.app.routes.admin_routes import admin_bp
    from src.app.routes.login_routes.auth_routes import auth_bp
    from src.app.routes.coleta_routes import coleta_bp
    from src.app.routes.dashboard_routes import dashboard_bp
    from src.app.routes.programming_routes import programming_bp
    from src.app.routes.hmi_routes import hmi_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(clp_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(auth_bp)
    app.register_blueprint(coleta_bp, url_prefix='/coleta')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(programming_bp, url_prefix='/programacao')
    app.register_blueprint(hmi_bp, url_prefix='/hmi')
    logger.info("Blueprints do frontend registados (APP_MODE=full)")
#     app.register_blueprint(alarm_bp, url_prefix='/alarms')
#     app.register_blueprint(polling_bp, url_prefix='/polling')
#     app.register_blueprint(api_bp, url_prefix='/api')

# def initialize_services(app):
#     """Inicializa serviços do sistema"""
#     from app.services.polling_service import PollingManager, DataProcessor
#     from app.services.backup_service import BackupManager
#     from app.services.security_service import AuditService
    
#     # Polling system
#     app.polling_manager = PollingManager(app, db)
#     app.data_processor = DataProcessor(app, db, app.polling_manager)
    
#     # Outros serviços
#     app.backup_manager = BackupManager(app)
#     app.audit_service = AuditService(db)
    
#     # Iniciar processamento de dados
#     app.data_processor.start()
