"""Application configuration powered by ``pydantic-settings``.

This module centralises the environment driven configuration used by the
project.  Settings are grouped into typed sections (database, secrets,
feature flags, demo mode, mail, etc.) to improve discoverability and avoid
string-based lookups scattered throughout the codebase.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from flask import Flask, current_app
from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
DEFAULT_DEV_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/scada"
DEFAULT_PROD_DB_URL = (
    "postgresql+psycopg2://postgres:postgres@localhost:5432/scada_prod"
)
DEFAULT_TEST_DB_URL = "sqlite:///:memory:"

DEFAULT_LOG_DIR = BASE_DIR.parent / "logs"
DEFAULT_BACKUP_DIR = BASE_DIR.parent / "backups"

DEFAULT_DEV_ENGINE_OPTIONS: Dict[str, Any] = {
    "pool_size": 30,
    "max_overflow": 50,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
    "echo_pool": False,
}

DEFAULT_PROD_ENGINE_OPTIONS: Dict[str, Any] = {
    "pool_size": 50,
    "max_overflow": 100,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
    "echo_pool": False,
}


class DatabaseSettings(BaseModel):
    """Database connection related configuration."""

    url: str = Field(
        default=DEFAULT_DEV_DB_URL,
        validation_alias=AliasChoices("DATABASE_URL", "SQLALCHEMY_DATABASE_URI"),
    )
    echo: bool = Field(
        default=False,
        validation_alias=AliasChoices("SQLALCHEMY_ECHO", "DATABASE_ECHO"),
    )
    engine_options: Dict[str, Any] = Field(
        default_factory=lambda: dict(DEFAULT_DEV_ENGINE_OPTIONS)
    )


class SecretsSettings(BaseModel):
    """Secret tokens and credentials."""

    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        validation_alias=AliasChoices("SECRET_KEY", "APP_SECRET_KEY"),
    )
    poller_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("POLLER_API_KEY", "APP_POLLER_API_KEY"),
    )


class FeatureFlags(BaseModel):
    """Feature toggles that change runtime behaviour."""

    app_mode: str = Field(default="full", validation_alias=AliasChoices("APP_MODE"))
    enable_polling: bool = Field(default=True, alias="ENABLE_POLLING")
    enable_backups: bool = Field(default=True, alias="ENABLE_BACKUPS")
    enable_email: bool = Field(default=True, alias="ENABLE_EMAIL")
    enable_seed_scripts: bool = Field(default=True, alias="ENABLE_SEED_SCRIPTS")


class DemoSettings(BaseModel):
    """Flags specific to the product demo mode."""

    enabled: bool = Field(
        default=False, validation_alias=AliasChoices("DEMO_MODE", "APP_DEMO_MODE")
    )
    disable_polling: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DEMO_DISABLE_POLLING", "APP_DEMO_DISABLE_POLLING"
        ),
    )
    read_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEMO_READ_ONLY", "APP_DEMO_READ_ONLY"),
    )
    seed_sample_data: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEMO_SEED_SAMPLE_DATA", "APP_DEMO_SEED_SAMPLE_DATA"),
    )


class MailSettings(BaseModel):
    """SMTP parameters used by the alarm notification service."""

    server: str = Field(default="localhost", validation_alias=AliasChoices("MAIL_SERVER"))
    port: int = Field(default=1025, validation_alias=AliasChoices("MAIL_PORT"))
    username: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("MAIL_USERNAME")
    )
    password: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("MAIL_PASSWORD")
    )
    use_tls: bool = Field(default=True, validation_alias=AliasChoices("MAIL_USE_TLS"))
    use_ssl: bool = Field(default=False, validation_alias=AliasChoices("MAIL_USE_SSL"))
    default_sender: str = Field(
        default="alarms@example.com",
        validation_alias=AliasChoices("MAIL_DEFAULT_SENDER"),
    )
    suppress_send: bool = Field(
        default=False, validation_alias=AliasChoices("MAIL_SUPPRESS_SEND")
    )


class AppSettings(BaseSettings):
    """Typed application configuration backed by environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Literal["development", "production", "testing"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "FLASK_ENV", "ENVIRONMENT"),
    )
    debug: bool = Field(default=False)
    testing: bool = Field(default=False)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    secrets: SecretsSettings = Field(default_factory=SecretsSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    demo: DemoSettings = Field(default_factory=DemoSettings)
    mail: MailSettings = Field(default_factory=MailSettings)
    cache_url: str = Field(
        default="redis://localhost:5432/0",
        validation_alias=AliasChoices("CACHE_REDIS_URL", "REDIS_URL"),
    )
    wtf_csrf_enabled: bool = Field(
        default=True, validation_alias=AliasChoices("WTF_CSRF_ENABLED")
    )
    session_cookie_secure: bool = Field(
        default=False, validation_alias=AliasChoices("SESSION_COOKIE_SECURE")
    )
    session_cookie_httponly: bool = Field(
        default=True, validation_alias=AliasChoices("SESSION_COOKIE_HTTPONLY")
    )
    session_cookie_samesite: str = Field(
        default="Lax", validation_alias=AliasChoices("SESSION_COOKIE_SAMESITE")
    )
    permanent_session_lifetime: timedelta = Field(default=timedelta(hours=8))
    log_dir: Path = Field(
        default=DEFAULT_LOG_DIR, validation_alias=AliasChoices("LOG_DIR")
    )
    backup_dir: Path = Field(
        default=DEFAULT_BACKUP_DIR, validation_alias=AliasChoices("BACKUP_DIR")
    )
    backup_retention_days: int = Field(
        default=30, validation_alias=AliasChoices("BACKUP_RETENTION_DAYS")
    )
    polling_default_interval_ms: int = Field(
        default=1000, validation_alias=AliasChoices("POLLING_DEFAULT_INTERVAL")
    )
    polling_max_errors: int = Field(
        default=5, validation_alias=AliasChoices("POLLING_MAX_ERRORS")
    )

    @field_validator("permanent_session_lifetime", mode="before")
    @classmethod
    def _coerce_lifetime(cls, value: Any) -> timedelta:
        if isinstance(value, timedelta):
            return value
        if isinstance(value, (int, float)):
            return timedelta(seconds=float(value))
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return timedelta(seconds=int(stripped))
            try:
                return timedelta(seconds=float(stripped))
            except ValueError:
                pass
        return timedelta(hours=8)

    def with_environment(self, environment: Optional[str]) -> "AppSettings":
        """Return a copy adjusted for the selected environment."""

        env = (environment or self.environment or "development").lower()
        db_settings = self.database
        mail_settings = self.mail
        features = self.features
        demo = self.demo

        debug = self.debug
        testing = self.testing
        csrf_enabled = self.wtf_csrf_enabled
        session_cookie_secure = self.session_cookie_secure

        if env == "development":
            debug = True
        elif env == "production":
            session_cookie_secure = True
            if db_settings.url == DEFAULT_DEV_DB_URL:
                db_settings = db_settings.model_copy(update={"url": DEFAULT_PROD_DB_URL})
            if db_settings.engine_options == DEFAULT_DEV_ENGINE_OPTIONS:
                db_settings = db_settings.model_copy(
                    update={"engine_options": dict(DEFAULT_PROD_ENGINE_OPTIONS)}
                )
        elif env == "testing":
            testing = True
            debug = False
            csrf_enabled = False
            db_settings = db_settings.model_copy(
                update={
                    "url": DEFAULT_TEST_DB_URL,
                    "engine_options": {},
                    "echo": False,
                }
            )
            mail_settings = mail_settings.model_copy(update={"suppress_send": True})
            features = features.model_copy(update={"enable_backups": False})

        if demo.enabled:
            features = features.model_copy(
                update={
                    "enable_polling": features.enable_polling
                    and not demo.disable_polling,
                    "enable_backups": features.enable_backups and not demo.read_only,
                    "enable_seed_scripts": features.enable_seed_scripts
                    and demo.seed_sample_data,
                }
            )

        return self.model_copy(
            update={
                "environment": env,
                "debug": debug,
                "testing": testing,
                "wtf_csrf_enabled": csrf_enabled,
                "session_cookie_secure": session_cookie_secure,
                "database": db_settings,
                "mail": mail_settings,
                "features": features,
            }
        )

    def as_flask_config(self) -> Dict[str, Any]:
        """Translate settings into the dict expected by ``Flask``."""

        return {
            "DEBUG": self.debug,
            "TESTING": self.testing,
            "SECRET_KEY": self.secrets.secret_key,
            "SQLALCHEMY_DATABASE_URI": self.database.url,
            "SQLALCHEMY_ECHO": self.database.echo,
            "SQLALCHEMY_ENGINE_OPTIONS": self.database.engine_options,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_RECORD_QUERIES": True,
            "CACHE_TYPE": "redis",
            "CACHE_REDIS_URL": self.cache_url,
            "WTF_CSRF_ENABLED": self.wtf_csrf_enabled,
            "SESSION_COOKIE_SECURE": self.session_cookie_secure,
            "SESSION_COOKIE_HTTPONLY": self.session_cookie_httponly,
            "SESSION_COOKIE_SAMESITE": self.session_cookie_samesite,
            "PERMANENT_SESSION_LIFETIME": self.permanent_session_lifetime,
            "LOG_DIR": str(self.log_dir),
            "BACKUP_DIR": str(self.backup_dir),
            "BACKUP_RETENTION_DAYS": self.backup_retention_days,
            "MAIL_SERVER": self.mail.server,
            "MAIL_PORT": self.mail.port,
            "MAIL_USERNAME": self.mail.username,
            "MAIL_PASSWORD": self.mail.password,
            "MAIL_USE_TLS": self.mail.use_tls,
            "MAIL_USE_SSL": self.mail.use_ssl,
            "MAIL_DEFAULT_SENDER": self.mail.default_sender,
            "MAIL_SUPPRESS_SEND": self.mail.suppress_send,
            "POLLING_DEFAULT_INTERVAL": self.polling_default_interval_ms,
            "POLLING_MAX_ERRORS": self.polling_max_errors,
            "APP_MODE": self.features.app_mode,
            "POLLER_API_KEY": self.secrets.poller_api_key,
        }


def load_settings(config_name: Optional[str] = None) -> AppSettings:
    """Instantiate :class:`AppSettings` applying environment overrides."""

    base = AppSettings()
    return base.with_environment(config_name)


def store_settings(app: Flask, settings: AppSettings) -> None:
    """Attach the settings object to the Flask application instance."""

    app.extensions["app_settings"] = settings
    app.config["APP_SETTINGS"] = settings


def get_app_settings(app: Optional[Flask] = None) -> AppSettings:
    """Return the settings registered on the Flask application."""

    app_obj = app or current_app
    settings = app_obj.extensions.get("app_settings")
    if isinstance(settings, AppSettings):
        return settings
    raise RuntimeError("AppSettings not initialised for this Flask application")


__all__ = [
    "AppSettings",
    "DatabaseSettings",
    "DemoSettings",
    "FeatureFlags",
    "MailSettings",
    "SecretsSettings",
    "get_app_settings",
    "load_settings",
    "store_settings",
]

