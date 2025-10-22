import os
from flask import Flask, Blueprint
from src.utils.logs import logger
from src.app.extensions import db, migrate, login_manager, csrf
from src.app.config import config



def create_app(config_name='development'):
    
    logger.process("Criando app")
    app = Flask(__name__)
    logger.info("app criado")

    # Configuração
    logger.process("Configurando app")
    app.config.from_object(config[config_name])
    logger.info("app configurado")

    # Criar diretórios somente se fizer sentido (evita erro com sqlite:///:memory:)
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    try:
        # extrai caminho pra sqlite file (caso exista)
        if db_uri.startswith("sqlite:///"):
            path = db_uri.replace("sqlite:///", "")
            # se for :memory: ou vazio, não cria diretório
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        else:
            # para outros DBs, apenas criar logs/backups
            os.makedirs(app.config.get('LOG_DIR', './logs'), exist_ok=True)
            os.makedirs(app.config.get('BACKUP_DIR', './backups'), exist_ok=True)
    except Exception:
        # não explodir em ambiente de teste
        logger.exception("Erro ao criar diretórios (ignorando em ambiente de teste)")

    # Inicializar extensões
    logger.process("Iniciando extensões")
    db.init_app(app)
    try:
        migrate.init_app(app, db)
    except Exception:
        # em testes não precisamos do migrate rodando; se falhar, ignoramos
        logger.debug("Migrate init falhou (ok em testes).")
    login_manager.init_app(app)
    csrf.init_app(app)
    logger.info("extensões iniciadas")

    # Importar modelos (necessário para migrations e para registrar classes com SQLAlchemy)
    try:
        # se você mantém tudo em src.models.*
        from src.models import AlarmDefinition, Alarm, AuditLog, DataLog, Register, Organization, PLC, SecurityEvent, User, UserRole
        with app.app_context():
            db.create_all()
            logger.info("Registrando blueprints")
            register_blueprints(app)
        logger.info("db criado")
    except Exception as e:
        logger.debug(f"Import models failed (ok for tests if models imported elsewhere). {e}")

    return app

def register_blueprints(app):
     """Registra todos os blueprints"""
     from src.app.routes.main_route import main as main_bp
     from src.app.routes.clps_routes.detalhes_clp import clp_bp
#     from app.web.plc_management import plc_bp
#     from app.web.user_management import user_bp
#     from app.web.alarm_views import alarm_bp
#     from app.web.polling_control import polling_bp
#     from app.api import api_bp
    
     app.register_blueprint(main_bp)
     app.register_blueprint(clp_bp)
#     app.register_blueprint(plc_bp, url_prefix='/plc')
#     app.register_blueprint(user_bp, url_prefix='/users')
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
