"""改密链路不需要设备码/信任设备的回归测试。"""

import pytest

from scripts import bydsj_client, query_service, security_center


def _fake_session(**overrides):
    session = {
        "user_id": 1,
        "token": "token123",
        "money": 0,
        "diamond": 0,
        "nickname": "nick",
        "total_infull_num": 0,
        "cannon": 0,
        "agent_id": 0,
        "act_agent_id": 0,
    }
    session.update(overrides)
    return session


def _mock_dashijie_login(monkeypatch, captured: dict | None = None):
    monkeypatch.setattr(query_service, "login_type_of", lambda account: "dashijie")

    def fake_login(account, password, android_id, proxy=None):
        if captured is not None:
            captured["android_id"] = android_id
        return {"username": "u", "md5": "m", "android_id": android_id}

    monkeypatch.setattr(bydsj_client, "login", fake_login)
    monkeypatch.setattr(
        bydsj_client,
        "get_token",
        lambda info, proxy=None: _fake_session(),
    )


def test_get_session_change_pwd_uses_default_device_code_when_empty(monkeypatch):
    """改密场景账号没填设备码时，直接用协议默认设备码，不再尝试连模拟器。"""
    captured = {}
    _mock_dashijie_login(monkeypatch, captured)

    session = security_center.get_session("123456", "pwd", require_device=False)

    assert captured["android_id"] == bydsj_client.ANDROID_ID
    assert session["device_code"] == bydsj_client.ANDROID_ID


def test_get_session_change_pwd_never_calls_device_resolver(monkeypatch):
    """改密场景不触发设备码解析（不会弹“未连接模拟器”）。"""

    def boom(*args, **kwargs):
        raise AssertionError("改密场景不应解析设备码")

    monkeypatch.setattr(bydsj_client, "resolve_android_id", boom)
    _mock_dashijie_login(monkeypatch)

    security_center.get_session("123456", "pwd", require_device=False)


def test_get_session_change_pwd_keeps_explicit_device_code(monkeypatch):
    """账号已填设备码时，改密场景仍使用该设备码。"""
    captured = {}
    _mock_dashijie_login(monkeypatch, captured)

    security_center.get_session(
        "123456", "pwd", android_id="abcdef1234567890", require_device=False
    )

    assert captured["android_id"] == "abcdef1234567890"


def test_get_session_default_does_not_require_device(monkeypatch):
    """登录/刷新默认不再要求设备码：未填设备码时用协议默认值，不触发模拟器解析。"""
    captured = {}
    _mock_dashijie_login(monkeypatch, captured)

    def boom(*args, **kwargs):
        raise AssertionError("默认场景不应解析设备码")

    monkeypatch.setattr(bydsj_client, "resolve_android_id", boom)

    session = security_center.get_session("123456", "pwd")
    assert captured["android_id"] == bydsj_client.ANDROID_ID
    assert session["device_code"] == bydsj_client.ANDROID_ID


def test_get_session_require_device_true_still_resolves(monkeypatch):
    """显式 require_device=True 时保留原逻辑：无设备码则触发设备码解析。"""
    monkeypatch.setattr(query_service, "login_type_of", lambda account: "dashijie")

    def fake_resolve(android_id=None):
        raise RuntimeError("未连接模拟器")

    monkeypatch.setattr(bydsj_client, "resolve_android_id", fake_resolve)

    with pytest.raises(RuntimeError, match="未连接模拟器"):
        security_center.get_session("123456", "pwd", require_device=True)
