import struct
import sys

import pytest

from scripts.bydsj_client import ProtocolError, get_bag
from scripts.bydsj_client import _resp_error_message, _response_cannon


def test_resp_error_message_utf8():
    resp = b"\x01\x00\x00\x00" + "您填写的昵称不存在,请重新输入".encode("utf-8") + b"\x00" * 32
    assert _resp_error_message(resp) == "您填写的昵称不存在,请重新输入"


def test_resp_error_message_short_response():
    assert _resp_error_message(b"\x01\x00\x00\x00") == ""
    assert _resp_error_message(b"") == ""


def test_resp_error_message_stops_at_first_null():
    resp = b"\x01\x00\x00\x00" + "高风险".encode("utf-8") + b"\x00" + b"junk"
    assert _resp_error_message(resp) == "高风险"


def test_response_cannon_at_offset_156():
    resp = bytearray(200)
    struct.pack_into("<I", resp, 156, 35000)
    assert _response_cannon(bytes(resp)) == 35000


def test_response_cannon_short_response():
    assert _response_cannon(b"\x00" * 100) == 0


def test_debug_response_safe_when_stderr_none():
    original = sys.stderr
    sys.stderr = None
    try:
        from scripts.bydsj_client import _debug_response

        _debug_response(b"\x01\x00\x00\x00", "login-response")
    finally:
        sys.stderr = original


def test_get_bag_raises_on_session_invalid(monkeypatch):
    from scripts import bydsj_client

    resp = (
        b"\xff\xff\xff\xff"
        + "本次登录已失效，重新登录后再试".encode("utf-8")
        + b"\x00" * 64
    )
    monkeypatch.setattr(
        bydsj_client,
        "_post",
        lambda *a, **k: resp.hex().encode("ascii"),
    )
    with pytest.raises(ProtocolError, match="本次登录已失效"):
        get_bag(382377872, "TOKEN123456789012")


def test_get_bag_success_parses_items(monkeypatch):
    from scripts import bydsj_client

    payload = struct.pack("<I", 2) + struct.pack("<II", 10301, 10) + struct.pack(
        "<II", 10311, 15
    )
    monkeypatch.setattr(
        bydsj_client,
        "_post",
        lambda *a, **k: payload.hex().encode("ascii"),
    )
    assert get_bag(382377872, "TOKEN123456789012") == {10301: 10, 10311: 15}
