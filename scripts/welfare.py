"""福利领取协议：VIP 每日福利 + 捕鱼感恩日 VIP尊享福利。

基于 2026-08-15 真机抓包逆向（见 dumps/20260815/抓包记录.md）：
  - VIP 每日福利领取：msgType 12476
  - 感恩日状态查询：msgType 2608 sub=0 act_id=1001
  - 感恩日 VIP尊享福利领取：msgType 2608 sub=1 act_id=1001
"""

from __future__ import annotations

import json
import struct

from scripts import bydsj_client

GAME_VER = bydsj_client.GAME_VER
AGENT_ID = bydsj_client.AGENT_ID

MSG_VIP_DAILY = 12476  # VIP 每日福利领取
MSG_ACTIVITY = 2608  # 活动通用（感恩日）
ACT_ID_THANKSGIVING = 1001  # 捕鱼感恩日 VIP尊享福利
TASK_CODE_C = 67  # 0x43 = 'C'：感恩日任务 C（VIP尊享福利）


def _pad(token: str, size: int) -> bytes:
    b = token.encode("ascii")
    if len(b) > size:
        raise bydsj_client.ProtocolError("token 过长")
    return b.ljust(size, b"\0")


def _post(msg_type: int, fields: bytes, proxy: str | None = None) -> bytes:
    raw = bydsj_client._post(
        bydsj_client.pack_request(msg_type, fields), proxy=proxy
    )
    return bydsj_client._decode_response(raw)


def _parse_json_response(resp: bytes) -> dict:
    text = resp.decode("utf-8", errors="replace")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise bydsj_client.ProtocolError(f"活动响应不是 JSON：{text[:120]!r}")
    return json.loads(text[start : end + 1])


def _fmt_rewards(items: dict[int, int]) -> str:
    return "、".join(
        f"{bydsj_client.item_name(pid)}×{num}" for pid, num in sorted(items.items())
    )


def format_thanksgiving_summary(claim: dict) -> str:
    """把感恩日领取响应 JSON 转成可读摘要，如“钻石×230、锁定×30、…”。"""
    parts = []
    fixed = [
        ("钻石", claim.get("iAwardDiamond", 0)),
        ("锁定", claim.get("iAwardLock", 0)),
        ("狂暴", claim.get("iAwardCrazy", 0)),
        ("冰冻", claim.get("iAwardFrozen", 0)),
    ]
    for name, num in fixed:
        if num:
            parts.append(f"{name}×{num}")
    prop_ids = claim.get("arrOtherAwardPropId") or []
    prop_nums = claim.get("arrOtherAwardPropNum") or []
    for pid, num in zip(prop_ids, prop_nums):
        if num:
            parts.append(f"{bydsj_client.item_name(pid)}×{num}")
    return "、".join(parts) or "无明细"


def claim_vip_daily(
    account_id: int, token: str, proxy: str | None = None
) -> dict:
    """领取 VIP 每日福利（msgType 12476）。返回 {result, items}。"""
    fields = (
        struct.pack("<I", account_id)
        + _pad(token, 20)
        + struct.pack("<II", GAME_VER, AGENT_ID)
    )
    resp = _post(MSG_VIP_DAILY, fields, proxy)
    if len(resp) < 12:
        raise bydsj_client.ProtocolError(f"VIP 每日福利响应过短: {len(resp)}")
    result = struct.unpack_from("<I", resp, 0)[0]
    if result != 0:
        detail = resp[4:].split(b"\0", 1)[0]
        suffix = detail.decode("utf-8", errors="replace").strip()
        raise bydsj_client.ProtocolError(
            f"VIP 每日福利领取失败 iResult={result}"
            + (f": {suffix}" if suffix else "")
        )
    count = struct.unpack_from("<I", resp, 8)[0]
    items: dict[int, int] = {}
    for i in range(count):
        off = 12 + i * 8
        if off + 8 > len(resp):
            break
        pid, num = struct.unpack_from("<II", resp, off)
        items[pid] = items.get(pid, 0) + num
    return {"result": result, "items": items, "summary": _fmt_rewards(items)}


def query_thanksgiving(
    account_id: int, token: str, proxy: str | None = None
) -> dict:
    """查询捕鱼感恩日 VIP尊享福利状态（2608 sub=0）。返回 JSON。"""
    fields = (
        struct.pack("<I", 0)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", ACT_ID_THANKSGIVING)
        + struct.pack("<I", account_id)
        + _pad(token, 16)
        + struct.pack("<Q", 0)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", AGENT_ID)
        + struct.pack("<I", 33)
    )
    return _parse_json_response(_post(MSG_ACTIVITY, fields, proxy))


def claim_thanksgiving(
    account_id: int,
    token: str,
    vip_level: int,
    proxy: str | None = None,
) -> dict:
    """领取捕鱼感恩日 VIP尊享福利（2608 sub=1）。返回奖励 JSON。"""
    vip_text = str(int(vip_level)).encode("ascii")
    fields = (
        struct.pack("<I", 1)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", ACT_ID_THANKSGIVING)
        + struct.pack("<I", account_id)
        + _pad(token, 16)
        + struct.pack("<Q", 0)
        + struct.pack("<I", TASK_CODE_C)
        + b"\0" * 20
        + vip_text
        + b"\0" * (184 - 64 - len(vip_text))
    )
    return _parse_json_response(_post(MSG_ACTIVITY, fields, proxy))


def claim_thanksgiving_full(
    account_id: int, token: str, proxy: str | None = None
) -> dict:
    """查询状态并领取感恩日 VIP尊享福利；不可领时抛出明确错误。"""
    status = query_thanksgiving(account_id, token, proxy)
    state = str(status.get("awardStateC", "0"))
    if state != "1":
        raise bydsj_client.ProtocolError(
            f"感恩日VIP尊享福利当前不可领取 (awardStateC={state})"
        )
    vip_level = int(status.get("vipLevel", 0))
    if vip_level <= 0:
        raise bydsj_client.ProtocolError(
            f"感恩日VIP尊享福利缺少 VIP 等级 (vipLevel={vip_level})"
        )
    claim = claim_thanksgiving(account_id, token, vip_level, proxy)
    return {"status": status, "claim": claim}


def _pack_vip_daily_fields(account_id: int, token: str) -> bytes:
    return (
        struct.pack("<I", account_id)
        + _pad(token, 20)
        + struct.pack("<II", GAME_VER, AGENT_ID)
    )


def _pack_thanksgiving_query_fields(account_id: int, token: str) -> bytes:
    return (
        struct.pack("<I", 0)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", ACT_ID_THANKSGIVING)
        + struct.pack("<I", account_id)
        + _pad(token, 16)
        + struct.pack("<Q", 0)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", AGENT_ID)
        + struct.pack("<I", 33)
    )


def _pack_thanksgiving_claim_fields(
    account_id: int, token: str, vip_level: int
) -> bytes:
    vip_text = str(int(vip_level)).encode("ascii")
    return (
        struct.pack("<I", 1)
        + struct.pack("<I", GAME_VER)
        + struct.pack("<I", ACT_ID_THANKSGIVING)
        + struct.pack("<I", account_id)
        + _pad(token, 16)
        + struct.pack("<Q", 0)
        + struct.pack("<I", TASK_CODE_C)
        + b"\0" * 20
        + vip_text
        + b"\0" * (184 - 64 - len(vip_text))
    )
