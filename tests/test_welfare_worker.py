"""福利批量领取 worker 测试：多类型顺序执行、单类型失败不中断、全部失败抛错。"""

from app import WelfareWorker
from scripts import security_center, welfare


def _worker(kinds):
    return WelfareWorker(
        store=None,
        accounts=[],
        pool=None,
        delay_min=0,
        delay_max=0,
        enabled=False,
        kinds=kinds,
    )


def _patch_run_and_claims(monkeypatch, order):
    def fake_run(store, account, password, device_code, proxy, fn=None, **kw):
        return fn({"user_id": 1, "token": "TOKEN"})

    monkeypatch.setattr(security_center, "run_with_session", fake_run)
    monkeypatch.setattr(
        welfare,
        "claim_vip_daily",
        lambda uid, token, proxy=None: order.append("vip_daily")
        or {"summary": "绿灵石×15"},
    )
    monkeypatch.setattr(
        welfare,
        "claim_thanksgiving_full",
        lambda uid, token, proxy=None: order.append("thanksgiving")
        or {"claim": {"iAwardLock": 30, "resultType": "1"}},
    )


def test_welfare_claim_fixed_order(monkeypatch):
    order = []
    _patch_run_and_claims(monkeypatch, order)
    worker = _worker(["vip_daily", "thanksgiving"])
    results = worker._claim({"account": "a", "password": "p", "device_code": ""}, None)
    assert order == ["vip_daily", "thanksgiving"]
    assert results["vip_daily"]["summary"] == "绿灵石×15"
    assert results["thanksgiving"]["claim"]["iAwardLock"] == 30


def test_welfare_partial_failure_continues(monkeypatch):
    def fake_run(store, account, password, device_code, proxy, fn=None, **kw):
        return fn({"user_id": 1, "token": "T"})

    monkeypatch.setattr(security_center, "run_with_session", fake_run)
    monkeypatch.setattr(
        welfare, "claim_vip_daily", lambda uid, token, proxy=None: {"summary": "ok"}
    )

    def raise_claimed(*a, **k):
        raise RuntimeError("感恩日VIP尊享福利当前不可领取")

    monkeypatch.setattr(welfare, "claim_thanksgiving_full", raise_claimed)
    worker = _worker(["vip_daily", "thanksgiving"])
    results = worker._claim({"account": "a", "password": "p", "device_code": ""}, None)
    assert results["vip_daily"]["summary"] == "ok"
    assert isinstance(results["thanksgiving"], Exception)


def test_welfare_all_failed_raises(monkeypatch):
    def fake_run(store, account, password, device_code, proxy, fn=None, **kw):
        return fn({"user_id": 1, "token": "T"})

    monkeypatch.setattr(security_center, "run_with_session", fake_run)

    def fail(*a, **k):
        raise RuntimeError("失败")

    monkeypatch.setattr(welfare, "claim_vip_daily", fail)
    monkeypatch.setattr(welfare, "claim_thanksgiving_full", fail)
    worker = _worker(["vip_daily", "thanksgiving"])
    import pytest

    with pytest.raises(RuntimeError, match="每日VIP福利：失败；感恩日VIP尊享福利：失败"):
        worker._claim({"account": "a", "password": "p", "device_code": ""}, None)


def test_welfare_single_kind_only(monkeypatch):
    order = []
    _patch_run_and_claims(monkeypatch, order)
    worker = _worker(["vip_daily"])
    results = worker._claim({"account": "a", "password": "p", "device_code": ""}, None)
    assert order == ["vip_daily"]
    assert list(results.keys()) == ["vip_daily"]
