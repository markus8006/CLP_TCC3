from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.app.routes.api import dashboard_api, historian_api, layout_api, manual_control_api, plc_api


@pytest.fixture(autouse=True)
def disable_login(app):
    original = app.config.get("LOGIN_DISABLED", False)
    app.config["LOGIN_DISABLED"] = True
    yield
    app.config["LOGIN_DISABLED"] = original


def test_dashboard_summary_uses_helper(app, client, monkeypatch):
    monkeypatch.setattr(
        dashboard_api,
        "build_dashboard_summary_payload",
        lambda: {"status": "ok"},
    )

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_layout_endpoint_relies_on_builder(app, client, monkeypatch):
    monkeypatch.setattr(
        layout_api,
        "build_layout_payload",
        lambda: {"layout": {"nodes": []}},
    )

    response = client.get("/api/dashboard/layout")
    assert response.status_code == 200
    assert response.get_json() == {"layout": {"nodes": []}}


def test_historian_export_uses_service(app, client, monkeypatch):
    fake_result = SimpleNamespace(
        file_path="/tmp/export.csv",
        rows=42,
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        historian_api, "historian_sync_service", SimpleNamespace(export_snapshot=lambda **_: fake_result)
    )

    import src.utils.role.roles as roles

    monkeypatch.setattr(roles, "current_user", SimpleNamespace(has_permission=lambda *_: True))

    response = client.post("/api/historian/export", json={"start": None, "end": None})
    assert response.status_code == 200
    assert response.get_json()["rows"] == 42


def test_manual_history_returns_commands(app, client, monkeypatch):
    command = SimpleNamespace(as_dict=lambda: {"id": 1})
    monkeypatch.setattr(
        manual_control_api, "manual_control_service", SimpleNamespace(recent_commands=lambda limit: [command])
    )

    response = client.get("/api/hmi/manual-commands")
    assert response.status_code == 200
    assert response.get_json() == {"commands": [{"id": 1}]}


def test_plc_tag_discovery_simulation(app, client, monkeypatch):
    monkeypatch.setattr(plc_api, "get_simulated_tags", lambda protocol: ["tag-a"])

    response = client.get("/api/tag-discovery/mock/simulate")
    assert response.status_code == 200
    assert response.get_json() == {"tags": ["tag-a"]}
