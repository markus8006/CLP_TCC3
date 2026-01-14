import os
from datetime import timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "t"}


class _RequiredEnv:
    """Descriptor that enforces the presence of mandatory environment variables."""

    def __init__(self, name: str, *, help_text: Optional[str] = None) -> None:
        self.name = name
        self.help_text = help_text
        self.attr_name: Optional[str] = None

    def __set_name__(self, owner, name) -> None:  # type: ignore[override]
        self.attr_name = name

    def __get__(self, instance, owner):  # type: ignore[override]
        value = os.environ.get(self.name)
        if value is None or value == "":
            readable = self.help_text or self.attr_name or self.name
            raise RuntimeError(
                f"Environment variable '{self.name}' is required to load '{readable}' "
                f"for {owner.__name__}. Configure it via your secret manager or .env file."
            )
        return value


basedir = Path(__file__).resolve().parent

# Load optional local overrides without affecting production environments.
load_dotenv(basedir.parent.parent / ".env", override=False)

class Config:
    # Chaves secretas
    SECRET_KEY = _RequiredEnv('SECRET_KEY', help_text='Flask SECRET_KEY')
    SQLALCHEMY_ECHO = False

    # Track modifications
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True

    # Cache
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:5432/0'

    # Banco de dados
    SQLALCHEMY_DATABASE_URI = _RequiredEnv('DATABASE_URL', help_text='SQLALCHEMY_DATABASE_URI')

    # Segurança / session
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Credenciais padrão para integração com PLCs
    PLC_DEFAULT_USERNAME = _RequiredEnv('PLC_DEFAULT_USERNAME', help_text='PLC default username')
    PLC_DEFAULT_PASSWORD = _RequiredEnv('PLC_DEFAULT_PASSWORD', help_text='PLC default password')
    PLC_SECRET_BACKEND_PATH = os.environ.get('PLC_SECRET_BACKEND_PATH')

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
    SECRET_KEY = 'testing-secret-key'
    PLC_DEFAULT_USERNAME = 'test-plc-user'
    PLC_DEFAULT_PASSWORD = 'test-plc-pass'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
