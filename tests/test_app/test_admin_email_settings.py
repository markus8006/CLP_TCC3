import pytest
from src.models.Users import User, UserRole
from src.services.email_settings_service import get_stored_email_settings


@pytest.fixture
def admin_user(db):
    user = User(username="admin", email="admin@example.com", role=UserRole.ADMIN)
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username="admin", password="secret"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def test_email_settings_requires_authentication(client):
    response = client.get("/admin/settings/email", follow_redirects=True)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Login" in page or "Utilizador" in page


def test_admin_can_update_email_settings(client, admin_user):
    login(client)

    response = client.get("/admin/settings/email")
    assert response.status_code == 200
    assert "Alertas por Email" in response.get_data(as_text=True)

    response = client.post(
        "/admin/settings/email",
        data={
            "mail_server": "smtp.admin.local",
            "mail_port": 2587,
            "mail_username": "alarms@admin.local",
            "mail_password": "super-secret",
            "mail_default_sender": "alarms@admin.local",
            "mail_use_tls": "y",
            "mail_suppress_send": "y",
            "submit": "Guardar configurações",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Configurações de email actualizadas." in page
    assert "smtp.admin.local" in page

    stored = get_stored_email_settings()
    assert stored["MAIL_SERVER"] == "smtp.admin.local"
    assert stored["MAIL_PORT"] == 2587
    assert stored["MAIL_USERNAME"] == "alarms@admin.local"
    assert stored["MAIL_DEFAULT_SENDER"] == "alarms@admin.local"
    assert stored["MAIL_USE_TLS"] is True
    assert stored["MAIL_SUPPRESS_SEND"] is True
