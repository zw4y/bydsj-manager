import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from scripts.heartbeat import HeartbeatPolicy


def test_first_failure_does_not_lock():
    policy = HeartbeatPolicy(interval_seconds=1800, grace_seconds=600)
    policy.record_failure(now=1000)
    assert policy.should_lock(now=1000) is False
    assert policy.should_lock(now=1599) is False


def test_lock_after_grace():
    policy = HeartbeatPolicy(interval_seconds=1800, grace_seconds=600)
    policy.record_failure(now=1000)
    assert policy.should_lock(now=1600) is True


def test_success_resets_failures():
    policy = HeartbeatPolicy(interval_seconds=1800, grace_seconds=600)
    policy.record_failure(now=1000)
    policy.record_success()
    assert policy.consecutive_failures == 0
    assert policy.should_lock(now=99999) is False


def test_consecutive_failures_count():
    policy = HeartbeatPolicy(interval_seconds=1800, grace_seconds=600)
    policy.record_failure(now=1)
    policy.record_failure(now=2)
    assert policy.consecutive_failures == 2


def test_interval_attribute():
    policy = HeartbeatPolicy(interval_seconds=1800, grace_seconds=600)
    assert policy.interval_seconds == 1800


class FakeAuthClient:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    def validate(self, key: str, machine: str) -> dict:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {"ok": True}


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    return app


def _run_thread(thread, signal_name: str, timeout_ms: int = 5000):
    from app import HeartbeatThread

    loop = QEventLoop()
    payload = {}
    getattr(thread, signal_name).connect(
        lambda *args: (payload.update(message=args[0] if args else ""), loop.quit())
    )
    thread.finished.connect(loop.quit)
    thread.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    thread.wait(2000)
    return payload


def test_heartbeat_thread_rejects_invalid_card(qapp):
    from app import HeartbeatThread
    from scripts.card_auth import CardAuthError

    thread = HeartbeatThread(
        "http://example.test",
        "card",
        interval_seconds=0,
        grace_seconds=600,
        retry_interval_seconds=0,
        client=FakeAuthClient(error=CardAuthError("卡密已过期")),
    )
    payload = _run_thread(thread, "rejected")
    assert payload["message"] == "卡密已过期"
    assert thread._client.calls >= 1


def test_heartbeat_thread_locks_after_network_failure(qapp):
    from app import HeartbeatThread

    thread = HeartbeatThread(
        "http://example.test",
        "card",
        interval_seconds=0,
        grace_seconds=0,
        retry_interval_seconds=0,
        client=FakeAuthClient(error=RuntimeError("timeout")),
    )
    payload = _run_thread(thread, "locked")
    assert "timeout" in payload["message"]
    assert thread._client.calls >= 1
