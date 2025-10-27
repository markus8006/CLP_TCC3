import os
from datetime import timedelta


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "t"}

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Chaves secretas
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_ECHO = False
    
    # Track modifications
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    
    # Cache
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:5432/0'
    
    # Segurança / session
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Polling
    POLLING_DEFAULT_INTERVAL = 1000  # ms
    POLLING_MAX_ERRORS = 5
    
    # Backup
    BACKUP_DIR = os.path.join(basedir, '..', 'backups')
    BACKUP_RETENTION_DAYS = 30
    
    # Logs
    LOG_LEVEL = 'INFO'
    LOG_DIR = os.path.join(basedir, '..', 'logs')

    # Email
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 1025))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = _env_bool('MAIL_USE_TLS', True)
    MAIL_USE_SSL = _env_bool('MAIL_USE_SSL', False)
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'alarms@example.com')
    MAIL_SUPPRESS_SEND = _env_bool('MAIL_SUPPRESS_SEND', False)

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False
    
    # ✅ ATUALIZADO: Usar PgBouncer na porta 5432
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql+psycopg2://postgres:postgres@localhost:5432/scada'
    
    # ✅ OTIMIZADO: Pool maior para aproveitar PgBouncer
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 30,           # Aumentado de 20
        'max_overflow': 50,        # Aumentado de 30
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'echo_pool': False,        # Desabilitar logs de pool
    }

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    
    # ✅ ATUALIZADO: Usar PgBouncer na porta 5432
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql+psycopg2://postgres:postgres@localhost:5432/scada_prod'
    
    # ✅ OTIMIZADO: Pool ainda maior para produção
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 50,           # Aumentado
        'max_overflow': 100,       # Mantido
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'pool_pre_ping': True,
        'echo_pool': False,
    }

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
