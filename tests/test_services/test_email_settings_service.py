import smtplib

import pytest

from src.services.email_settings_service import (
    get_email_settings,
    get_stored_email_settings,
    update_email_settings,
)
from src.services.email_service import send_email
from src.app.settings import get_app_settings, store_settings


@pytest.mark.usefixtures("db")
class TestEmailSettingsService:
    def test_defaults_are_returned_when_no_customisation(self, app):
        original_settings = get_app_settings(app)
        default_mail = original_settings.mail.model_copy(
            update={
                "server": "smtp.default.local",
                "port": 1026,
                "username": "default@example.com",
                "password": "default-pass",
                "default_sender": "alarms@default.com",
                "use_tls": True,
                "use_ssl": False,
                "suppress_send": False,
            }
        )
        store_settings(app, original_settings.model_copy(update={"mail": default_mail}))

        try:
            settings = get_email_settings()
            assert settings["MAIL_SERVER"] == "smtp.default.local"
            assert settings["MAIL_PORT"] == 1026
            assert settings["MAIL_USE_TLS"] is True
            assert settings["MAIL_SUPPRESS_SEND"] is False

            stored = get_stored_email_settings()
            assert all(value is None for value in stored.values())

            update_email_settings({
                "MAIL_SERVER": "smtp.persisted.local",
                "MAIL_PORT": 2525,
                "MAIL_USE_TLS": False,
            })

            settings = get_email_settings()
            assert settings["MAIL_SERVER"] == "smtp.persisted.local"
            assert settings["MAIL_PORT"] == 2525
            assert settings["MAIL_USE_TLS"] is False

            stored = get_stored_email_settings()
            assert stored["MAIL_SERVER"] == "smtp.persisted.local"
            assert stored["MAIL_PORT"] == 2525

            update_email_settings({"MAIL_SERVER": None})
            assert get_stored_email_settings()["MAIL_SERVER"] is None
            assert get_email_settings()["MAIL_SERVER"] == "smtp.default.local"
        finally:
            store_settings(app, original_settings)

    def test_send_email_uses_persisted_configuration(self, app, monkeypatch):
        original_settings = get_app_settings(app)
        store_settings(
            app,
            original_settings.model_copy(
                update={
                    "mail": original_settings.mail.model_copy(update={"suppress_send": False})
                }
            ),
        )

        update_email_settings(
            {
                "MAIL_SERVER": "smtp.example.com",
                "MAIL_PORT": 2525,
                "MAIL_USERNAME": "alerts@example.com",
                "MAIL_PASSWORD": "secret",
                "MAIL_DEFAULT_SENDER": "alerts@example.com",
                "MAIL_USE_TLS": True,
                "MAIL_USE_SSL": False,
                "MAIL_SUPPRESS_SEND": False,
            }
        )

        class DummySMTP:
            last = None

            def __init__(self, host, port, timeout=10):
                self.host = host
                self.port = port
                self.timeout = timeout
                self.started_tls = False
                self.login_args = None
                self.messages = []
                DummySMTP.last = self

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def starttls(self):
                self.started_tls = True

            def login(self, username, password):
                self.login_args = (username, password)

            def send_message(self, message):
                self.messages.append(message)

        monkeypatch.setattr(smtplib, "SMTP", DummySMTP)
        monkeypatch.setattr(smtplib, "SMTP_SSL", DummySMTP)

        try:
            result = send_email("Teste", "Corpo", ["dest@example.com"])

            assert result is True
            smtp_instance = DummySMTP.last
            assert smtp_instance is not None
            assert smtp_instance.host == "smtp.example.com"
            assert smtp_instance.port == 2525
            assert smtp_instance.started_tls is True
            assert smtp_instance.login_args == ("alerts@example.com", "secret")
            assert smtp_instance.messages

            message = smtp_instance.messages[-1]
            assert message["From"] == "alerts@example.com"
            assert message["To"] == "dest@example.com"
            assert "Teste" in message["Subject"]
            assert message.get_content().strip() == "Corpo"
        finally:
            store_settings(app, original_settings)

    def test_send_email_honours_suppress_flag(self, app, monkeypatch):
        original_settings = get_app_settings(app)
        store_settings(
            app,
            original_settings.model_copy(
                update={
                    "mail": original_settings.mail.model_copy(update={"suppress_send": False})
                }
            ),
        )
        update_email_settings({"MAIL_SUPPRESS_SEND": True})

        called = {"smtp": False}

        def _fail(*args, **kwargs):  # pragma: no cover - defensive
            called["smtp"] = True
            raise AssertionError("SMTP should not be invoked when suppressed")

        monkeypatch.setattr(smtplib, "SMTP", _fail)
        monkeypatch.setattr(smtplib, "SMTP_SSL", _fail)

        try:
            result = send_email("Teste", "Corpo", ["dest@example.com"])

            assert result is True
            assert called["smtp"] is False
        finally:
            store_settings(app, original_settings)
