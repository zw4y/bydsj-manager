"""个人仓库：查询仓库、存入/取出道具（REPO_PROP_INFO_MSG=0xE3, REPO_PROP_DEAL_MSG=0xE4）。"""

from __future__ import annotations

import hashlib
import struct

from scripts.bydsj_client import _decode_response, _post, pack_request

REPO_INFO_MSG = 0xE3
REPO_DEAL_MSG = 0xE4
GOLD_PROP_ID = 10000
GOLD_DISPLAY_RATIO = 10000
BULLET_PROP_IDS = {12003, 12004, 12006, 12005}
BULLET_MAX = 999


def display_to_deal_num(prop_id: int, display_quantity: int) -> int:
    """把界面显示数量转成底层提交数量。金币按亿换算，其他道具原样。"""
    if prop_id == GOLD_PROP_ID:
        return display_quantity * GOLD_DISPLAY_RATIO
    return display_quantity


def display_unit(prop_id: int) -> str:
    return "亿" if prop_id == GOLD_PROP_ID else "个"


def deal_max_display(prop_id: int, source_raw: int) -> int:
    """计算存取弹窗的最大可输入数量（显示单位）。

    弹头类道具输入上限固定 999；金币按亿显示；其他道具按原始数量。
    """
    if prop_id == GOLD_PROP_ID:
        return source_raw // GOLD_DISPLAY_RATIO
    if prop_id in BULLET_PROP_IDS:
        return min(source_raw, BULLET_MAX)
    return source_raw


def adjust_bag_gold(bag_raw: int, deal_num: int) -> int:
    """金币存取后本地推算背包金币（协议 raw 单位=万）。

    deal_num 正数=存入（背包减少），负数=取出（背包增加）。
    显示值(亿) = raw ÷ 10000；提交值 = 输入(亿) × 10000（见 display_to_deal_num）。
    """
    return bag_raw - deal_num


def get_repo(
    user_id: int,
    token: str,
    agent_id: int = 10000046,
    version_num: int = 602,
    proxy: str | None = None,
) -> dict[int, int]:
    body = (
        struct.pack("<II", user_id, version_num)
        + struct.pack("<I", agent_id)
        + token.encode("ascii").ljust(20, b"\0")
    )
    raw = _decode_response(
        _post(pack_request(REPO_INFO_MSG, body), proxy=proxy)
    )
    if len(raw) < 8:
        raise RuntimeError(f"仓库响应过短: {len(raw)}")
    result, prop_num = struct.unpack_from("<II", raw, 0)
    if result != 0:
        raise RuntimeError(f"查询仓库失败 result={result}")
    items: dict[int, int] = {}
    for i in range(prop_num):
        off = 8 + i * 8
        if off + 8 > len(raw):
            break
        pid, num = struct.unpack_from("<II", raw, off)
        items[pid] = num
    return items


def repo_deal(
    user_id: int,
    token: str,
    prop_id: int,
    deal_num: int,
    trade_password: str,
    version_num: int = 602,
    proxy: str | None = None,
) -> dict:
    """deal_num 正数=存入，负数=取出。返回 {result, leftRepoNum} 或 {result, msgText}。"""
    pwd_md5 = hashlib.md5(trade_password.encode("utf-8")).hexdigest()
    body = (
        struct.pack("<I", user_id)
        + token.encode("ascii").ljust(20, b"\0")
        + struct.pack("<IIi", version_num, prop_id, deal_num)
        + pwd_md5.encode("ascii").ljust(36, b"\0")
    )
    raw = _decode_response(
        _post(pack_request(REPO_DEAL_MSG, body), proxy=proxy)
    )
    if len(raw) < 4:
        raise RuntimeError(f"仓库操作响应过短: {len(raw)}")
    result = struct.unpack_from("<I", raw, 0)[0]
    if result == 0 and len(raw) >= 8:
        left = struct.unpack_from("<I", raw, 4)[0]
        return {"result": 0, "leftRepoNum": left}
    msg = raw[4:132].rstrip(b"\0").decode("utf-8", errors="replace") if len(raw) >= 132 else ""
    return {"result": result, "msgText": msg}
