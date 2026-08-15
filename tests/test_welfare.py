"""welfare.py 协议封包与响应解析测试（样本来自 2026-08-15 抓包）。"""

import pytest

from scripts import bydsj_client
from scripts import welfare

AID = 382377872
TOKEN = "VYIKQIHMJNY2EX2L"


def test_pack_vip_daily_matches_capture():
    got = welfare._pack_vip_daily_fields(AID, TOKEN)
    assert got.hex() == (
        "909fca165659494b5149484d4a4e59324558324c000000005a020000ae969800"
    )


def test_pack_thanksgiving_query_matches_capture():
    got = welfare._pack_thanksgiving_query_fields(AID, TOKEN)
    assert got.hex() == (
        "000000005a020000e9030000909fca165659494b5149484d4a4e59324558324c"
        "00000000000000005a020000ae96980021000000"
    )


def test_pack_thanksgiving_claim_matches_capture():
    got = welfare._pack_thanksgiving_claim_fields(AID, TOKEN, 21)
    assert len(got) == 184
    assert got.hex() == (
        "010000005a020000e9030000909fca165659494b5149484d4a4e59324558324c"
        "000000000000000043000000" + "00" * 20 + "3231" + "00" * (184 - 66)
    )


def test_claim_vip_daily_parses_response(monkeypatch):
    raw = (
        "000000001500000005000000472800000f000000482800000f000000"
        "492800000f0000004a2800000f0000003d2800000a000000"
    )
    monkeypatch.setattr(
        welfare,
        "_post",
        lambda *a, **k: bydsj_client._decode_response(raw.encode()),
    )
    result = welfare.claim_vip_daily(AID, TOKEN)
    assert result["result"] == 0
    assert result["items"] == {
        10311: 15,
        10312: 15,
        10313: 15,
        10314: 15,
        10301: 10,
    }
    assert "绿灵石×15" in result["summary"]


def test_claim_vip_daily_raises_on_error(monkeypatch):
    raw = b"\x01\x00\x00\x00" + "已领取".encode() + b"\0"
    monkeypatch.setattr(welfare, "_post", lambda *a, **k: raw)
    with pytest.raises(bydsj_client.ProtocolError, match="已领取"):
        welfare.claim_vip_daily(AID, TOKEN)


def test_parse_thanksgiving_json_with_trailing_garbage():
    resp = b'{"vipLevel":21,"awardStateC":"1","resultType":"1"}\x00\x00\x03\x00\x00'
    parsed = welfare._parse_json_response(resp)
    assert parsed["vipLevel"] == 21
    assert parsed["awardStateC"] == "1"


def test_claim_thanksgiving_full_query_not_claimable(monkeypatch):
    monkeypatch.setattr(
        welfare,
        "query_thanksgiving",
        lambda *a, **k: {"vipLevel": 15, "awardStateC": "0"},
    )
    with pytest.raises(bydsj_client.ProtocolError, match="不可领取"):
        welfare.claim_thanksgiving_full(AID, TOKEN)


def test_claim_thanksgiving_full_success(monkeypatch):
    monkeypatch.setattr(
        welfare,
        "query_thanksgiving",
        lambda *a, **k: {"vipLevel": 15, "awardStateC": "1"},
    )
    monkeypatch.setattr(
        welfare,
        "claim_thanksgiving",
        lambda aid, tok, level, proxy=None: {
            "iAwardLock": 30,
            "resultType": "1",
        },
    )
    result = welfare.claim_thanksgiving_full(AID, TOKEN)
    assert result["claim"]["iAwardLock"] == 30
