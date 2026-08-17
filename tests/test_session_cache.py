"""会话缓存测试：加密存取、指纹作废、失效识别、自动重登重试一次。"""

import pytest

from scripts import bydsj_client, security_center, warehouse
from scripts.card_auth import derive_key
from scripts.local_store import LocalAccountStore


def _make_store(tmp_path) -> LocalAccountStore:
    return LocalAccountStore(
        str(tmp_path / "a.db"), derive_key("card", "machine", b"salt")
    )


def _session(**overrides) -> dict:
    session = {
        "user_id": 382377872,
        "token": "CACHEDTOKEN123456",
        "money": 100,
        "diamond": 5,
        "nickname": "测试账号",
        "account": "acc1",
        "device_code": "",
        "_fp": "",
    }
    session.update(overrides)
    return session


def test_save_load_clear_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    store.save_session("acc1", _session())
    loaded = store.load_session("acc1")
    assert loaded["token"] == "CACHEDTOKEN123456"
    assert loaded["nickname"] == "测试账号"
    store.clear_session("acc1")
    assert store.load_session("acc1") is None


def test_load_session_missing_or_corrupt(tmp_path):
    store = _make_store(tmp_path)
    assert store.load_session("不存在") is None


def test_fingerprint_changes_on_credentials():
    base = security_center.session_fingerprint("acc", "p1", None, "passport")
    assert base != security_center.session_fingerprint("acc", "p2", None, "passport")
    assert base != security_center.session_fingerprint("acc", "p1", "dev", "passport")
    assert base != security_center.session_fingerprint("acc", "p1", None, "dashijie")


def test_is_session_invalid():
    invalid = [
        "本次登录已失效，重新登录后再试",
        "背包查询失败 iResult=4294967295: 本次登录已失效，重新登录后再试",
        "查询仓库失败 result=4294967295",
        "登录已失效",
    ]
    for text in invalid:
        assert security_center.is_session_invalid(RuntimeError(text)), text
    valid = [
        "login failed, iResult=1: 高风险的昵称登录,请稍后再试",
        "网络错误 urlopen error",
        "仓库操作响应过短",
        "",
    ]
    for text in valid:
        assert not security_center.is_session_invalid(RuntimeError(text)), text


def test_get_cached_session_reuses_without_login(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    fp = security_center.session_fingerprint("acc1", "pwd", None, "passport")
    store.save_session("acc1", _session(_fp=fp))
    login_calls = []
    monkeypatch.setattr(
        security_center,
        "get_session",
        lambda *a, **k: login_calls.append(1) or _session(),
    )
    session = security_center.get_cached_session(store, "acc1", "pwd", None)
    assert session["token"] == "CACHEDTOKEN123456"
    assert login_calls == []


def test_get_cached_session_force_relogin(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    fp = security_center.session_fingerprint("acc1", "pwd", None, "passport")
    store.save_session("acc1", _session(_fp=fp, token="OLD"))
    login_calls = []

    def fake_login(*a, **k):
        login_calls.append(1)
        return _session(token="NEW")

    monkeypatch.setattr(security_center, "get_session", fake_login)
    session = security_center.get_cached_session(
        store, "acc1", "pwd", None, force=True
    )
    assert session["token"] == "NEW"
    assert store.load_session("acc1")["token"] == "NEW"
    assert login_calls == [1]


def test_get_cached_session_fingerprint_mismatch_relogins(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    old_fp = security_center.session_fingerprint("acc1", "old", None, "passport")
    store.save_session("acc1", _session(_fp=old_fp, token="OLD"))
    login_calls = []

    def fake_login(*a, **k):
        login_calls.append(1)
        return _session(token="NEW")

    monkeypatch.setattr(security_center, "get_session", fake_login)
    session = security_center.get_cached_session(store, "acc1", "pwd", None)
    assert session["token"] == "NEW"
    assert login_calls == [1]


def test_run_with_session_relogin_once_on_invalid(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    fp = security_center.session_fingerprint("acc1", "pwd", None, "passport")
    store.save_session("acc1", _session(_fp=fp, token="BADTOKEN"))

    def fake_login(*a, **k):
        return _session(token="GOODTOKEN")

    monkeypatch.setattr(security_center, "get_session", fake_login)
    used = []
    relogin_calls = []

    def fn(session):
        used.append(session["token"])
        if session["token"] == "BADTOKEN":
            raise bydsj_client.ProtocolError("本次登录已失效，重新登录后再试")
        return "ok"

    result = security_center.run_with_session(
        store,
        "acc1",
        "pwd",
        None,
        fn=fn,
        on_relogin=lambda: relogin_calls.append(1),
    )
    assert result == "ok"
    assert used == ["BADTOKEN", "GOODTOKEN"]
    assert relogin_calls == [1]
    assert store.load_session("acc1")["token"] == "GOODTOKEN"


def test_run_with_session_no_retry_on_other_error(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    fp = security_center.session_fingerprint("acc1", "pwd", None, "passport")
    store.save_session("acc1", _session(_fp=fp, token="BADTOKEN"))
    login_calls = []
    monkeypatch.setattr(
        security_center,
        "get_session",
        lambda *a, **k: login_calls.append(1) or _session(token="NEW"),
    )

    def fn(session):
        raise RuntimeError("login failed, iResult=1: 高风险的昵称登录")

    with pytest.raises(RuntimeError, match="高风险的昵称登录"):
        security_center.run_with_session(
            store, "acc1", "pwd", None, fn=fn
        )
    assert login_calls == []  # 非失效错误不重登
    assert store.load_session("acc1")["token"] == "BADTOKEN"


def test_two_refreshes_only_one_login(monkeypatch, tmp_path):
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    login_calls = []
    monkeypatch.setattr(
        security_center,
        "get_session",
        lambda *a, **k: login_calls.append(1) or _session(),
    )
    monkeypatch.setattr(
        bydsj_client, "get_bag", lambda uid, token, proxy=None: {10301: 10}
    )
    cached_flags = []

    def refresh():
        return security_center.run_with_session(
            store,
            "acc1",
            "pwd",
            None,
            fn=lambda s: bydsj_client.get_bag(s["user_id"], s["token"]),
            on_cached=lambda: cached_flags.append(True),
        )

    assert refresh() == {10301: 10}
    assert refresh() == {10301: 10}
    assert login_calls == [1]
    assert cached_flags == [True]


def test_deal_then_refresh_no_relogin(monkeypatch, tmp_path):
    """存取（如弹头存入仓库）后刷新：全程复用缓存会话，不再登录。"""
    store = _make_store(tmp_path)
    store.add_account("acc1", "pwd", "", "passport")
    login_calls = []
    monkeypatch.setattr(
        security_center,
        "get_session",
        lambda *a, **k: login_calls.append(1) or _session(),
    )
    monkeypatch.setattr(
        bydsj_client,
        "get_bag",
        lambda uid, token, proxy=None: {12003: 20},
    )
    monkeypatch.setattr(
        warehouse,
        "get_repo",
        lambda uid, token, **k: {12003: 10},
    )
    monkeypatch.setattr(
        warehouse,
        "repo_deal",
        lambda uid, token, prop_id, deal_num, trade_password, **k: {
            "result": 0,
            "leftRepoNum": 20,
        },
    )

    def refresh():
        return security_center.run_with_session(
            store,
            "acc1",
            "pwd",
            None,
            fn=lambda s: {
                "bag": bydsj_client.get_bag(s["user_id"], s["token"]),
                "repo": warehouse.get_repo(s["user_id"], s["token"]),
            },
        )

    before = refresh()  # 首次：登录一次建立缓存
    session = security_center.get_cached_session(store, "acc1", "pwd", None)
    deal = warehouse.repo_deal(
        session["user_id"], session["token"], 12003, 10, "二级密码"
    )
    after = refresh()  # 存取后刷新：不再登录

    assert before == {"bag": {12003: 20}, "repo": {12003: 10}}
    assert after == before
    assert deal["leftRepoNum"] == 20
    assert login_calls == [1]


def test_db_migration_adds_enc_session_column(tmp_path):
    store = _make_store(tmp_path)
    with store._connect() as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(accounts)")]
    assert "enc_session" in columns
