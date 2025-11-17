from datetime import datetime, timedelta, timezone

from src.app.routes import main_route


class DummyPLC:
    def __init__(
        self,
        *,
        is_online=False,
        last_seen=None,
        polling_interval=1000,
        timeout=5000,
    ):
        self.is_online = is_online
        self.last_seen = last_seen
        self.polling_interval = polling_interval
        self.timeout = timeout


def test_is_plc_online_respects_online_flag():
    plc = DummyPLC(is_online=True, last_seen=None)

    assert main_route._is_plc_online(plc) is True


def test_is_plc_online_allows_recent_last_seen():
    now = datetime.now(timezone.utc)
    plc = DummyPLC(is_online=False, last_seen=now - timedelta(seconds=1))

    assert main_route._is_plc_online(plc, now=now) is True


def test_is_plc_online_expires_after_grace_period():
    now = datetime.now(timezone.utc)
    grace_seconds = main_route._grace_period_seconds(DummyPLC())
    plc = DummyPLC(
        is_online=False,
        last_seen=now - timedelta(seconds=grace_seconds + 1),
    )

    assert main_route._is_plc_online(plc, now=now) is False
