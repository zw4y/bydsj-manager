"""Minimal protocol client for 捕鱼大世界 (com.shiyi.by3d).

Wire format (reverse engineered from captured traffic):
  HTTP POST https://i.bydsj3d.com/BKBY3DHttpReq/HandleHttpReq.do
  body = "v=" + UPPERHEX(payload)
  payload = u16 msgType + u16 version(33) + fields + ASCII_UPPERHEX(MD5(payload[:-32] + KEY))

Messages implemented:
  type 4    - 大世界登录 (account + md5(password))
  type 6659 - 获取会话 token
  type 8    - 背包道具列表
"""

import hashlib
import struct
import sys
import time
import urllib.request
from pathlib import Path

URL = "https://i.bydsj3d.com/BKBY3DHttpReq/HandleHttpReq.do"
TOKENLOGIN_URL = "https://i.bydsj3d.com/BKBY3DHttpReq/TokenLoginReq.do"
KEY = b"qwerpoiuasdflkjh"
PROTO_VER = 33
AGENT_ID = 10000046
GAME_VER = 602

# 会话失效信号（抓包实证：iResult=0xFFFFFFFF + “本次登录已失效，重新登录后再试”）
SESSION_INVALID_RESULT = 0xFFFFFFFF
SESSION_INVALID_KEYWORDS = ("登录已失效", "登录失效", "重新登录", "4294967295")

# 设备画像（来自抓包样本，后续可做成每账号/实例配置）
ANDROID_ID = "157bc3df28f459f0"


def resolve_android_id(android_id: str | None = None) -> str:
    if android_id:
        return android_id
    try:
        from scripts.device_info import get_device_code
    except ImportError:
        from device_info import get_device_code

    return get_device_code()


def _replace_android_id(data: bytes, android_id: str) -> bytes:
    if not android_id or android_id == ANDROID_ID:
        return data
    return data.replace(ANDROID_ID.encode("ascii"), android_id.encode("ascii"))

# type 6659 请求模板（从真实抓包提取的 866 字节 payload）
FLOW5_TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "data" / "flow5_template.bin"
FLOW5_TEMPLATE_LEGACY = Path(__file__).resolve().parent.parent / "dumps" / "20260810" / "protocol" / "flow5_template.bin"
CAPTURE_FILE = Path(__file__).resolve().parent.parent / "dumps" / "20260810" / "capture_final.mitm"
TOKENLOGIN_TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "data" / "tokenlogin_template.bin"

# 内部资源 ID -> 名称（用户提供的完整对照表，后续扩展用）
ITEM_NAMES = {
    10000: "金币",
    20000: "钻石",
    10231: "优惠卷",
    10300: "神灯",
    10301: "锁定",
    10302: "冰冻",
    10304: "狂暴",
    10305: "号角",
    10311: "绿灵石",
    10312: "金刚石",
    10313: "紫金石",
    10314: "血精石",
    10315: "精华",
    11001: "鱼卷",
    11002: "点卷",
    12003: "青铜弹头",
    12004: "白银弹头",
    12006: "黄金弹头",
    12005: "白金弹头",
    31001: "好运卡",
    31037: "强化宝石",
    31038: "荣耀币",
    31039: "荣耀水晶",
    31047: "翡翠币",
    31048: "翡翠水晶",
    31051: "聚财币",
    31052: "聚财水晶",
    31062: "忠义剑",
    31065: "同心结",
    31075: "将军令",
    31080: "霸业旗",
    31106: "军师策",
    31104: "精魄",
    31135: "相思佩",
    31073: "战魂宝箱",
    31098: "英雄残魂",
}

# 客户端当前展示的道具（11 个核心 + 新增 6 个）
ITEMS = [
    (10000, "金币"),
    (10305, "号角"),
    (10315, "精华"),
    (31073, "战魂宝箱"),
    (12005, "白金弹头"),
    (12006, "黄金弹头"),
    (12004, "白银弹头"),
    (12003, "青铜弹头"),
    (10300, "神灯"),
    (10301, "锁定"),
    (10302, "冰冻"),
    (10304, "狂暴"),
    (10311, "绿灵石"),
    (10312, "金刚石"),
    (10313, "紫金石"),
    (10314, "血精石"),
]

ITEM_NAMES = dict(ITEMS)


def item_name(prop_id: int) -> str:
    """把内部道具 ID 转成展示名称，未知 ID 回退为 ID 本身。"""
    return ITEM_NAMES.get(prop_id, f"未知道具({prop_id})")


class ProtocolError(RuntimeError):
    pass


def _pad(s: str, size: int) -> bytes:
    b = s.encode("utf-8")
    if len(b) > size:
        raise ProtocolError(f"field too long: {s!r} > {size}")
    return b.ljust(size, b"\0")


def pack_request(msg_type: int, body: bytes) -> bytes:
    payload = struct.pack("<HH", msg_type, PROTO_VER) + body
    sig = hashlib.md5(payload + KEY).hexdigest().upper().encode("ascii")
    full = payload + sig
    return b"v=" + full.hex().upper().encode("ascii")


def _post(
    data: bytes, timeout: float = 20.0, url: str = URL, proxy: str | None = None
) -> bytes:
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def _decode_response(raw: bytes) -> bytes:
    s = raw.decode("ascii", errors="strict")
    if len(s) % 2 or not all(c in "0123456789ABCDEFabcdef" for c in s):
        raise ProtocolError("response is not hex-encoded")
    return bytes.fromhex(s)


def _resp_error_message(resp: bytes) -> str:
    """从失败响应里提取服务器返回的中文提示（iResult 之后、以 \\0 结尾）。"""
    if len(resp) <= 4:
        return ""
    raw = resp[4:].split(b"\0", 1)[0]
    return raw.decode("utf-8", errors="replace").strip()


def _response_cannon(resp: bytes) -> int:
    """登录会话响应偏移 156 的当前炮倍（万单位，如 35000）。"""
    return struct.unpack_from("<I", resp, 156)[0] if len(resp) >= 160 else 0


def _debug_response(resp: bytes, label: str = "response"):
    if sys.stderr is None:
        return
    sys.stderr.write(f"[debug] {label} len={len(resp)} hex={resp[:160].hex(' ')}\n")
    sys.stderr.write(f"[debug] {label} asc={''.join(chr(c) if 32 <= c < 127 else '.' for c in resp[:160])}\n")


def login(
    account: str,
    password: str,
    android_id: str | None = None,
    proxy: str | None = None,
) -> dict:
    """大世界登录：type 4。返回内部用户名与 md5。"""
    android_id = resolve_android_id(android_id)
    body = (
        _pad(android_id, 40)
        + _pad(account, 32)
        + _pad(hashlib.md5(password.encode("utf-8")).hexdigest(), 40)
        + struct.pack("<II", AGENT_ID, GAME_VER)
    )
    raw = _post(pack_request(4, body), proxy=proxy)
    resp = _decode_response(raw)
    if len(resp) < 64:
        raise ProtocolError(f"login response too short: {len(resp)}")
    result = struct.unpack_from("<I", resp, 0)[0]
    if result != 0:
        _debug_response(resp, "login-response")
        detail = _resp_error_message(resp)
        suffix = f": {detail}" if detail else ""
        raise ProtocolError(f"login failed, iResult={result}{suffix}")
    username = resp[4:24].rstrip(b"\0").decode("utf-8", errors="replace")
    md5hex = resp[24:64].rstrip(b"\0").decode("ascii", errors="replace")
    return {"username": username, "md5": md5hex, "android_id": android_id}


def _load_flow5_template() -> bytes:
    """读取 type 6659 请求模板（866 字节 payload）。优先独立文件，缺失时从抓包文件提取。"""
    if FLOW5_TEMPLATE_FILE.exists():
        data = FLOW5_TEMPLATE_FILE.read_bytes()
        if len(data) == 866 and int.from_bytes(data[0:2], "little") == 6659:
            return data
    if FLOW5_TEMPLATE_LEGACY.exists():
        data = FLOW5_TEMPLATE_LEGACY.read_bytes()
        if len(data) == 866 and int.from_bytes(data[0:2], "little") == 6659:
            return data
    try:
        from mitmproxy import io
    except ImportError:
        raise ProtocolError("mitmproxy 未安装，无法加载模板（开发环境需要）")
    if not CAPTURE_FILE.exists():
        raise ProtocolError(f"抓包文件不存在: {CAPTURE_FILE}")
    with CAPTURE_FILE.open("rb") as f:
        for fl in io.FlowReader(f).stream():
            raw = fl.request.content
            if raw.startswith(b"v=") and len(raw) > 4:
                payload = bytes.fromhex(raw[2:].decode())
                if len(payload) == 866 and int.from_bytes(payload[0:2], "little") == 6659:
                    return payload
    raise ProtocolError("抓包文件中没有 type 6659 模板")


def get_token(
    login_info: dict, timestamp: int | None = None, proxy: str | None = None
) -> dict:
    """type 6659：用内部用户名+md5 换取 token 和 userID。"""
    android_id = resolve_android_id(login_info.get("android_id"))
    tmpl = bytearray(_replace_android_id(_load_flow5_template(), android_id))
    username = login_info["username"].encode("utf-8")
    md5hex = login_info["md5"].encode("ascii")
    if len(username) > 128 or len(md5hex) > 40:
        raise ProtocolError("username/md5 too long")
    tmpl[12 : 12 + 128] = username.ljust(128, b"\0")
    tmpl[140 : 140 + 40] = md5hex.ljust(40, b"\0")
    if timestamp is None:
        timestamp = int(time.time())
    struct.pack_into("<I", tmpl, 324, timestamp)
    struct.pack_into("<I", tmpl, 4, len(tmpl) - 32)  # iSelfLen

    raw = _post(pack_request(6659, bytes(tmpl[4:])), proxy=proxy)
    resp = _decode_response(raw)
    if len(resp) < 60:
        raise ProtocolError(f"token response too short: {len(resp)}")
    user_id = struct.unpack_from("<I", resp, 32)[0]
    token = resp[36:56].rstrip(b"\0").decode("ascii", errors="replace")
    if not token:
        _debug_response(resp, "token-response")
        raise ProtocolError(f"token empty (iResult={struct.unpack_from('<I', resp, 0)[0]})")
    money = struct.unpack_from("<I", resp, 128)[0] if len(resp) >= 136 else 0
    diamond = struct.unpack_from("<I", resp, 132)[0] if len(resp) >= 136 else 0
    nickname = resp[56:88].rstrip(b"\0").decode("utf-8", errors="replace")
    total_infull_num = struct.unpack_from("<I", resp, 140)[0] if len(resp) >= 144 else 0
    cannon = _response_cannon(resp)
    agent_id = struct.unpack_from("<I", resp, 272)[0] if len(resp) >= 280 else 0
    act_agent_id = struct.unpack_from("<I", resp, 276)[0] if len(resp) >= 280 else 0
    return {
        "user_id": user_id,
        "token": token,
        "money": money,
        "diamond": diamond,
        "nickname": nickname,
        "total_infull_num": total_infull_num,
        "cannon": cannon,
        "agent_id": agent_id,
        "act_agent_id": act_agent_id,
    }


def get_bag(user_id: int, token: str, proxy: str | None = None) -> dict[int, int]:
    """type 8：背包道具列表。返回 {道具ID: 数量}。"""
    body = struct.pack("<I", user_id) + _pad(token, 20)
    raw = _post(pack_request(8, body), proxy=proxy)
    resp = _decode_response(raw)
    if len(resp) < 4:
        raise ProtocolError("bag response too short")
    count = struct.unpack_from("<I", resp, 0)[0]
    if count == SESSION_INVALID_RESULT:
        detail = _resp_error_message(resp)
        suffix = f": {detail}" if detail else ""
        raise ProtocolError(f"背包查询失败 iResult={count}{suffix}")
    items = {}
    for i in range(count):
        off = 4 + i * 8
        if off + 8 > len(resp):
            break
        pid, num = struct.unpack_from("<II", resp, off)
        items[pid] = num
    return items


def get_repo_raw(user_id: int, token: str) -> bytes:
    """type 12349：仓库道具信息，返回原始解码字节（格式待解析）。"""
    body = (
        struct.pack("<I", user_id)
        + _pad(token, 20)
        + struct.pack("<II", GAME_VER, AGENT_ID)
    )
    raw = _post(pack_request(12349, body))
    return _decode_response(raw)


def token_login(
    lc_token: str,
    android_id: str | None = None,
    proxy: str | None = None,
) -> dict:
    """通行证登录：用 Gaia 返回的 LC_ token 换取游戏会话（type 6674）。"""
    if not TOKENLOGIN_TEMPLATE_FILE.exists():
        raise ProtocolError(f"token 登录模板不存在: {TOKENLOGIN_TEMPLATE_FILE}")
    android_id = resolve_android_id(android_id)
    tmpl = bytearray(_replace_android_id(TOKENLOGIN_TEMPLATE_FILE.read_bytes(), android_id))
    if not lc_token.startswith("LC_") or len(lc_token) != 35:
        raise ProtocolError("LC_ token 格式不正确")
    off = tmpl.find(b"LC_")
    if off < 0:
        raise ProtocolError("模板中未找到 LC_ token 字段")
    tmpl[off : off + 35] = lc_token.encode("ascii")
    sig = hashlib.md5(bytes(tmpl[:-32]) + KEY).hexdigest().upper().encode("ascii")
    tmpl[-32:] = sig

    raw = _post(
        pack_request(6674, bytes(tmpl[4:])), url=TOKENLOGIN_URL, proxy=proxy
    )
    resp = _decode_response(raw)
    if len(resp) < 60:
        raise ProtocolError(f"token 登录响应过短: {len(resp)}")
    result = struct.unpack_from("<I", resp, 0)[0]
    if result != 0:
        detail = _resp_error_message(resp)
        suffix = f": {detail}" if detail else ""
        raise ProtocolError(f"token 登录失败, iResult={result}{suffix}")
    username = resp[12:32].rstrip(b"\0").decode("utf-8", errors="replace")
    user_id = struct.unpack_from("<I", resp, 32)[0]
    token = resp[36:56].rstrip(b"\0").decode("ascii", errors="replace")
    if not token:
        raise ProtocolError("token 为空")
    money = struct.unpack_from("<I", resp, 128)[0] if len(resp) >= 136 else 0
    diamond = struct.unpack_from("<I", resp, 132)[0] if len(resp) >= 136 else 0
    nickname = resp[56:88].rstrip(b"\0").decode("utf-8", errors="replace")
    total_infull_num = struct.unpack_from("<I", resp, 140)[0] if len(resp) >= 144 else 0
    cannon = _response_cannon(resp)
    agent_id = struct.unpack_from("<I", resp, 272)[0] if len(resp) >= 280 else 0
    act_agent_id = struct.unpack_from("<I", resp, 276)[0] if len(resp) >= 280 else 0
    return {
        "username": username,
        "user_id": user_id,
        "token": token,
        "money": money,
        "diamond": diamond,
        "nickname": nickname,
        "total_infull_num": total_infull_num,
        "cannon": cannon,
        "agent_id": agent_id,
        "act_agent_id": act_agent_id,
    }


def query_with_token(lc_token: str, android_id: str | None = None) -> dict:
    session = token_login(lc_token, android_id)
    bag = get_bag(session["user_id"], session["token"])
    return {
        "account": lc_token,
        "username": session["username"],
        "user_id": session["user_id"],
        "money": session["money"],
        "diamond": session["diamond"],
        "items": {pid: bag.get(pid, 0) for pid, _ in ITEMS},
    }


def query(
    account: str,
    password: str,
    android_id: str | None = None,
    proxy: str | None = None,
) -> dict:
    login_info = login(account, password, android_id, proxy)
    token_info = get_token(login_info, proxy=proxy)
    bag = get_bag(token_info["user_id"], token_info["token"], proxy)
    return {
        "account": account,
        "username": login_info["username"],
        "user_id": token_info["user_id"],
        "money": token_info["money"],
        "diamond": token_info["diamond"],
        "items": {pid: bag.get(pid, 0) for pid, _ in ITEMS},
    }


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--token":
        result = query_with_token(sys.argv[2])
        print(f"LC token: {result['account']}  内部用户: {result['username']}  userID: {result['user_id']}")
        for pid, name in ITEMS:
            count = result["items"][pid]
            if pid == 10000:
                count = f"{result['money'] // 10000}亿"
            elif pid == 20000:
                count = result["diamond"]
            print(f"  {name}: {count}")
        return
    if len(sys.argv) < 3:
        print("usage: python bydsj_client.py <账号> <密码> | --token <LC_xxx>", file=sys.stderr)
        sys.exit(1)
    result = query(sys.argv[1], sys.argv[2])
    print(f"账号: {result['account']}  内部用户: {result['username']}  userID: {result['user_id']}")
    for pid, name in ITEMS:
        count = result["items"][pid]
        if pid == 10000:
            count = f"{result['money'] // 10000}亿"
        elif pid == 20000:
            count = result["diamond"]
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
