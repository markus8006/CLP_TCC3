import os
from flask import Flask
from app.extensions import db, migrate, login_manager, csrf, cache, socketio
from app.config import config



def create_app(config_name='development'):
    app = Flask(__name__)
    
    # Configuração
    app.config.from_object(config[config_name])
    
    # Criar diretórios necessários
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)
    os.makedirs(app.config['BACKUP_DIR'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')), exist_ok=True)
    
    # Inicializar extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    
    # Importar modelos (necessário para migrations)
    from src.models import AlarmDefinition, Alarm, AuditLog, DataLog, Register, Organization, PLC, SecurityEvent
    
    # Registrar blueprints
    register_blueprints(app)
    
    # Inicializar serviços
    initialize_services(app)
    
    # Configurar logging
    configure_logging(app)
    
    return app

def register_blueprints(app):
    """Registra todos os blueprints"""
    from app.auth.routes import auth_bp
    from app.web.main import main_bp
    from app.web.plc_management import plc_bp
    from app.web.user_management import user_bp
    from app.web.alarm_views import alarm_bp
    from app.web.polling_control import polling_bp
    from app.api import api_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(plc_bp, url_prefix='/plc')
    app.register_blueprint(user_bp, url_prefix='/users')
    app.register_blueprint(alarm_bp, url_prefix='/alarms')
    app.register_blueprint(polling_bp, url_prefix='/polling')
    app.register_blueprint(api_bp, url_prefix='/api')

def initialize_services(app):
    """Inicializa serviços do sistema"""
    from app.services.polling_service import PollingManager, DataProcessor
    from app.services.backup_service import BackupManager
    from app.services.security_service import AuditService
    
    # Polling system
    app.polling_manager = PollingManager(app, db)
    app.data_processor = DataProcessor(app, db, app.polling_manager)
    
    # Outros serviços
    app.backup_manager = BackupManager(app)
    app.audit_service = AuditService(db)
    
    # Iniciar processamento de dados
    app.data_processor.start()

def configure_logging(app):
    """Configura sistema de logs"""
    import logging
    from logging.handlers import RotatingFileHandler
    
    if not app.debug:
        # Log de aplicação
        log_file = os.path.join(app.config['LOG_DIR'], 'app.log')
        file_handler = RotatingFileHandler(log_file, maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Sistema SCADA iniciado')
