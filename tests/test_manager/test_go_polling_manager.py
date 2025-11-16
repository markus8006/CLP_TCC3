import logging

from src.manager.go_polling_manager import GoPollingManager


def test_classify_stderr_line_info():
    level = GoPollingManager._classify_stderr_line(
        "2025/11/16 11:22:18 gRPC polling server listening on [::]:50051"
    )
    assert level == logging.INFO


def test_classify_stderr_line_warning():
    level = GoPollingManager._classify_stderr_line(
        "2025/11/16 WARN configuration reloaded"
    )
    assert level == logging.WARNING


def test_classify_stderr_line_error_keywords():
    level = GoPollingManager._classify_stderr_line(
        "2025/11/16 ERROR fatal panic stack trace"
    )
    assert level == logging.ERROR
