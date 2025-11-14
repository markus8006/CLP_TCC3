from src.app.extensions import db, login_manager
from src.app.settings import get_app_settings
from src.models.Users import User, UserRole


def test_app_uses_testing_config(app):
    settings = get_app_settings(app)
    assert settings.testing is True
    assert settings.database.url == "sqlite:///:memory:"
    assert settings.wtf_csrf_enabled is False


def test_blueprints_are_registered(app):
    for blueprint_name in ("main", "clp_bp", "auth", "apii"):
        assert blueprint_name in app.blueprints


def test_login_manager_user_loader(app, db):
    user = User(username="tester", email="tester@example.com", role=UserRole.ADMIN)
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    loaded = login_manager._user_callback(str(user.id))
    assert loaded is not None
    assert loaded.id == user.id
