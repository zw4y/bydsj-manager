import json
import time
import urllib.request

import pytest

from scripts.proxy_pool import (
    ProxyPool,
    fetch_proxies,
    mask_proxy,
)


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, response: FakeResponse):
        self._response = response

    def open(self, req, timeout=15.0):
        return self._response


def _patch_api(monkeypatch, payload: dict):
    def fake_build_opener(*args, **kwargs):
        return FakeOpener(FakeResponse(json.dumps(payload).encode("utf-8")))

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)


def _patch_api_text(monkeypatch, text: str):
    def fake_build_opener(*args, **kwargs):
        return FakeOpener(FakeResponse(text.encode("utf-8")))

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)


def test_fetch_single_object(monkeypatch):
    _patch_api(
        monkeypatch,
        {
            "ret": 200,
            "ip": "1.2.3.4",
            "port": "8080",
            "user": "u1",
            "pwd": "p1",
            "deadline": "2026-08-12 12:00:00",
        },
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert len(entries) == 1
    assert entries[0]["proxy"] == "http://u1:p1@1.2.3.4:8080"


def test_fetch_array_and_wrapped(monkeypatch):
    _patch_api(
        monkeypatch,
        {
            "ret": 200,
            "data": [
                {"ip": "1.1.1.1", "port": 1001, "user": "a", "pwd": "b"},
                {"ip": "2.2.2.2", "port": 1002, "user": "c", "pwd": "d"},
            ],
        },
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert [e["host"] for e in entries] == ["1.1.1.1:1001", "2.2.2.2:1002"]


def test_fetch_wrapped_list_key(monkeypatch):
    _patch_api(
        monkeypatch,
        {"ret": 200, "list": [{"ip": "3.3.3.3", "port": 99, "user": "u", "pwd": "p"}]},
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert entries[0]["proxy"] == "http://u:p@3.3.3.3:99"


def test_fetch_error_ret_raises(monkeypatch):
    _patch_api(monkeypatch, {"ret": 500, "msg": "bad key"})
    with pytest.raises(RuntimeError, match="bad key"):
        fetch_proxies("http://api.test/")


def test_proxy_url_encodes_credentials():
    entries = fetch_proxies
    from scripts.proxy_pool import _build_proxy_url

    assert (
        _build_proxy_url("host", 8080, "a b", "p@ss:word")
        == "http://a%20b:p%40ss%3Aword@host:8080"
    )


def test_fetch_txt_tab_separated(monkeypatch):
    _patch_api_text(
        monkeypatch,
        "1.1.1.1\t8080\tu1\tp1\t2026-08-12 12:00:00\n"
        "2.2.2.2\t8081\tu2\tp2\t2026-08-12 12:01:00",
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert len(entries) == 2
    assert entries[0]["proxy"] == "http://u1:p1@1.1.1.1:8080"
    assert entries[1]["host"] == "2.2.2.2:8081"


def test_fetch_txt_space_and_colon(monkeypatch):
    _patch_api_text(
        monkeypatch,
        "3.3.3.3 8082 u3 p3\n4.4.4.4:8083:u4:p4",
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert len(entries) == 2
    assert entries[0]["proxy"] == "http://u3:p3@3.3.3.3:8082"
    assert entries[1]["proxy"] == "http://u4:p4@4.4.4.4:8083"


def test_fetch_txt_ip_port_only(monkeypatch):
    _patch_api_text(
        monkeypatch,
        "183.141.199.67:2115\r\n110.82.14.4:1300",
    )
    entries = fetch_proxies("http://api.test/?lifetime=3")
    assert len(entries) == 2
    assert entries[0]["proxy"] == "http://183.141.199.67:2115"
    assert entries[1]["host"] == "110.82.14.4:1300"


def test_fetch_txt_unrecognized_raises(monkeypatch):
    _patch_api_text(monkeypatch, "not a proxy line")
    with pytest.raises(RuntimeError, match="无法识别"):
        fetch_proxies("http://api.test/")


def test_deadline_fallback_uses_lifetime(monkeypatch):
    _patch_api(
        monkeypatch,
        {"ret": 200, "ip": "1.2.3.4", "port": 1, "user": "u", "pwd": "p"},
    )
    entries = fetch_proxies("http://api.test/?lifetime=5")
    now = time.time()
    assert entries[0]["deadline_ts"] > now + 4 * 60
    assert entries[0]["deadline_ts"] <= now + 6 * 60


def test_pool_cap_and_refill(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(api_url, timeout=15.0):
        calls["n"] += 1
        hosts = ["1.1.1.1:1", "2.2.2.2:2"] if calls["n"] == 1 else ["3.3.3.3:3"]
        return [
            {
                "proxy": f"http://u:p@{host}",
                "deadline_ts": time.time() + 300,
                "used": 0,
                "host": host,
            }
            for host in hosts
        ]

    monkeypatch.setattr("scripts.proxy_pool.fetch_proxies", fake_fetch)
    pool = ProxyPool("http://api.test/", per_ip_cap=1)
    first = pool.next()
    second = pool.next()
    assert first != second
    assert calls["n"] == 1
    third = pool.next()
    assert third is not None and third != first and third != second
    assert calls["n"] == 2


def test_pool_mark_failed_removes_entry(monkeypatch):
    pool = ProxyPool(per_ip_cap=8)
    pool._entries = [
        {
            "proxy": "http://u:p@1.1.1.1:1",
            "deadline_ts": time.time() + 300,
            "used": 0,
            "host": "1.1.1.1:1",
        }
    ]
    pool.mark_failed("http://u:p@1.1.1.1:1")
    assert pool.next() is None


def test_mask_proxy_hides_credentials():
    assert mask_proxy("http://user:secret@1.2.3.4:8080") == "1.2.3.4:8080"
