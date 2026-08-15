"""Gaia (passport) login client for 捕鱼大世界.

Reverse engineered from the Gaia SDK inside com.shiyi.by3d:
  - login message type 258 (LOGIN_ACCOUNT)
  - password is sent as lowercase MD5 hex
  - request body is the protobuf ProtoRequestMsg (fields 1..17)
  - signature is MD5(values sorted by key + clientSignKey)

The successful response contains openToken which the game later uses as the
"LC_..." token for TokenLoginReq.do (type 6674).
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# From assets/reunionChannel (decrypted with gaia_cipher.py)
APP_ID = "600769507487"
CHANNEL_ID = 1
SECONDARY_CHANNEL_ID = 101013
APP_VERSION = "6.02.10"
REUNION_SDK_VERSION = "1.18.2"
CHANNEL_SDK_VERSION = "3.0.4"
CP_CHANNEL_ID = 10000046
APC_ID = 22
PCK_NAME = "com.shiyi.by3d"

# SHA1 of the APK signing certificate (from META-INF/YUZHUANG.RSA)
PCK_SIGNATURE = "AB:1F:51:AF:0E:0C:7C:D3:29:AB:5A:C2:B8:28:54:E6:75:97:0D:E4"

# From assets/keyInfo (decrypted with gaia_cipher.py)
CLIENT_SIGN_KEY = "yhfxjxcvojwocgmwwc"
REQUEST_PATH = "/api/data/v3/handleMsg"
PROD_URL = "https://dawn.shiyiyx.com"

ANDROID_ID = "157bc3df28f459f0"

_PHONE_RE = re.compile(r"^1\d{10}$")
MSG_TYPE_MOBILE_PWD_LOGIN = 291


def is_mobile_account(account: str) -> bool:
    """11 位手机号（1 开头），通行证支持手机号 + 密码登录。"""
    return bool(_PHONE_RE.fullmatch(account.strip()))


def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _f_int(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


def _f_str(field: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return _tag(field, 2) + _varint(len(data)) + data


def _f_msg(field: int, data: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(data)) + data


def build_base_msg(
    *,
    muid: str = "",
    mac: str = "",
    oaid: str = "",
    android_id: str = ANDROID_ID,
    platform: int = 1,
    client_id: str = "",
    ua: str = "",
    fingerprint_id: str = "",
) -> bytes:
    out = bytearray()
    out += _f_str(1, muid)
    out += _f_str(2, mac)
    out += _f_str(3, oaid)
    out += _f_str(4, android_id)
    out += _f_int(5, platform)
    out += _f_str(8, client_id)
    out += _f_str(11, ua)
    out += _f_str(12, fingerprint_id)
    return bytes(out)


def generate_sign(
    *,
    msg_type: int,
    user_name: str | None = None,
    password_md5: str | None = None,
    timestamp: int,
    open_id: str | None = None,
    open_token: str | None = None,
    apc_id: int = APC_ID,
    cp_user_id: int = 0,
    cp_user_token: str | None = None,
    expand_data: str | None = None,
    extra: dict[str, str] | None = None,
    include_apc_id: bool = True,
) -> str:
    values: dict[str, str] = {
        "appId": APP_ID,
        "appVersion": APP_VERSION,
        "channelId": str(CHANNEL_ID),
        "channelSdkVersion": CHANNEL_SDK_VERSION,
        "msgType": str(msg_type),
        "pckName": PCK_NAME,
        "pckSignature": PCK_SIGNATURE,
        "reunionSdkVersion": REUNION_SDK_VERSION,
        "secondaryChannelId": str(SECONDARY_CHANNEL_ID),
        "timestamp": str(timestamp),
    }
    if include_apc_id:
        values["apcId"] = str(apc_id)
        values["cpUserId"] = str(cp_user_id)
    if user_name is not None:
        values["userName"] = user_name
    if password_md5 is not None:
        values["password"] = password_md5
    if open_id is not None:
        values["openId"] = open_id
    if open_token is not None:
        values["openToken"] = open_token
    if cp_user_token is not None:
        values["cpUserToken"] = cp_user_token
    if expand_data is not None:
        values["expandData"] = expand_data
    if extra:
        values.update(extra)
    raw = "".join(values[k] for k in sorted(values)) + CLIENT_SIGN_KEY
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_login_request(user_name: str, password_md5: str, timestamp: int | None = None) -> bytes:
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    sign = generate_sign(
        msg_type=258,
        user_name=user_name,
        password_md5=password_md5,
        timestamp=timestamp,
    )
    func_msg = json.dumps(
        {
            "userName": user_name,
            "password": password_md5,
            "apcId": APC_ID,
            "cpUserId": 0,
            "cpUserToken": "",
            "expandData": "",
        },
        separators=(",", ":"),
    )
    out = bytearray()
    out += _f_int(1, 258)
    out += _f_str(2, APP_ID)
    out += _f_str(3, APP_VERSION)
    out += _f_str(4, REUNION_SDK_VERSION)
    out += _f_str(5, CHANNEL_SDK_VERSION)
    out += _f_int(6, CHANNEL_ID)
    out += _f_str(7, str(SECONDARY_CHANNEL_ID))
    out += _f_str(8, "")
    out += _f_str(9, "")
    out += _f_str(10, PCK_NAME)
    out += _f_int(11, timestamp)
    out += _f_int(12, CP_CHANNEL_ID)
    out += _f_str(13, sign)
    out += _f_msg(14, build_base_msg())
    out += _f_str(15, func_msg)
    out += _f_str(16, PCK_SIGNATURE)
    out += _f_int(17, 0)
    return bytes(out)


def build_quick_auth_request(
    open_id: str,
    open_token: str,
    timestamp: int | None = None,
    login_type: int = 2,
    cancel_cool_down: int = 0,
    sign_open_id: bool = True,
    sign_open_token: bool = True,
    extra_sign: dict[str, str] | None = None,
) -> bytes:
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    sign = generate_sign(
        msg_type=294,
        user_name="",
        password_md5="",
        timestamp=timestamp,
        open_id=open_id if sign_open_id else None,
        open_token=open_token if sign_open_token else None,
        extra={
            "loginType": str(login_type),
            "cancelCoolDown": str(cancel_cool_down),
            **(extra_sign or {}),
        },
        include_apc_id=False,
    )
    func_msg = json.dumps(
        {"loginType": login_type, "cancelCoolDown": cancel_cool_down},
        separators=(",", ":"),
    )
    out = bytearray()
    out += _f_int(1, 294)
    out += _f_str(2, APP_ID)
    out += _f_str(3, APP_VERSION)
    out += _f_str(4, REUNION_SDK_VERSION)
    out += _f_str(5, CHANNEL_SDK_VERSION)
    out += _f_int(6, CHANNEL_ID)
    out += _f_str(7, str(SECONDARY_CHANNEL_ID))
    out += _f_str(8, open_id)
    out += _f_str(9, open_token)
    out += _f_str(10, PCK_NAME)
    out += _f_int(11, timestamp)
    out += _f_int(12, CP_CHANNEL_ID)
    out += _f_str(13, sign)
    out += _f_msg(14, build_base_msg())
    out += _f_str(15, func_msg)
    out += _f_str(16, PCK_SIGNATURE)
    out += _f_int(17, 0)
    return bytes(out)


def post_gaia(
    body: bytes, timeout: float = 20.0, proxy: str | None = None
) -> dict:
    url = PROD_URL + REQUEST_PATH
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("User-Agent", "okhttp/4.9.2")
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"raw": raw.hex(), "rawText": raw.decode("utf-8", errors="replace")}


def post_login(
    user_name: str,
    password: str,
    timeout: float = 20.0,
    proxy: str | None = None,
) -> dict:
    password_md5 = md5_hex(password)
    body = build_login_request(user_name, password_md5)
    return post_gaia(body, timeout, proxy)


def gaia_login(
    user_name: str, password: str, proxy: str | None = None
) -> dict:
    data = post_login(user_name, password, proxy=proxy)
    ret = data.get("ret", data.get("code"))
    if ret not in (0, 1000, None):
        raise RuntimeError(f"Gaia login failed ret={ret} msg={data.get('msg', data)}")
    d = data.get("data") or {}
    return {
        "ret": ret,
        "userId": d.get("userId"),
        "userName": d.get("userName"),
        "nickName": d.get("nickName"),
        "mobile": d.get("mobile"),
        "openId": d.get("openId"),
        "openToken": d.get("openToken"),
        "raw": data,
    }


def build_mobile_pwd_login_request(
    mobile: str,
    password_md5: str,
    timestamp: int | None = None,
) -> bytes:
    """手机号 + 密码登录（msgType 291）。"""
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    sign = generate_sign(
        msg_type=MSG_TYPE_MOBILE_PWD_LOGIN,
        timestamp=timestamp,
        extra={
            "mobile": mobile,
            "password": password_md5,
            "apcId": str(APC_ID),
        },
        include_apc_id=False,
    )
    func_msg = json.dumps(
        {"mobile": mobile, "password": password_md5, "apcId": APC_ID},
        separators=(",", ":"),
    )
    out = bytearray()
    out += _f_int(1, MSG_TYPE_MOBILE_PWD_LOGIN)
    out += _f_str(2, APP_ID)
    out += _f_str(3, APP_VERSION)
    out += _f_str(4, REUNION_SDK_VERSION)
    out += _f_str(5, CHANNEL_SDK_VERSION)
    out += _f_int(6, CHANNEL_ID)
    out += _f_str(7, str(SECONDARY_CHANNEL_ID))
    out += _f_str(8, "")
    out += _f_str(9, "")
    out += _f_str(10, PCK_NAME)
    out += _f_int(11, timestamp)
    out += _f_int(12, CP_CHANNEL_ID)
    out += _f_str(13, sign)
    out += _f_msg(14, build_base_msg())
    out += _f_str(15, func_msg)
    out += _f_str(16, PCK_SIGNATURE)
    out += _f_int(17, 0)
    return bytes(out)


def gaia_mobile_pwd_login(
    mobile: str, password: str, proxy: str | None = None
) -> dict:
    data = post_gaia(build_mobile_pwd_login_request(mobile, md5_hex(password)), proxy=proxy)
    ret = data.get("ret", data.get("code"))
    if ret not in (0, 1000, None):
        raise RuntimeError(
            f"手机号密码登录失败 ret={ret} msg={data.get('msg', data)}"
        )
    d = data.get("data") or {}
    return {
        "ret": ret,
        "userId": d.get("userId"),
        "userName": d.get("userName"),
        "nickName": d.get("nickName"),
        "mobile": d.get("mobile"),
        "openId": d.get("openId"),
        "openToken": d.get("openToken"),
        "raw": data,
    }


def login_user(user_name: str, password: str, proxy: str | None = None) -> dict:
    """按账号类型选择通行证登录方式：手机号走手机号 + 密码，其他走账号密码。"""
    if is_mobile_account(user_name):
        return gaia_mobile_pwd_login(user_name, password, proxy)
    return gaia_login(user_name, password, proxy)


def gaia_quick_auth(
    open_id: str,
    open_token: str,
    login_type: int = 2,
    cancel_cool_down: int = 0,
    proxy: str | None = None,
) -> dict:
    body = build_quick_auth_request(open_id, open_token, login_type=login_type, cancel_cool_down=cancel_cool_down)
    data = post_gaia(body, proxy=proxy)
    ret = data.get("ret", data.get("code"))
    if ret not in (0, 1000, None):
        raise RuntimeError(f"Gaia quick auth failed ret={ret} msg={data.get('msg', data)}")
    d = data.get("data") or {}
    return {
        "ret": ret,
        "authCode": d.get("authCode"),
        "unreadNum": d.get("unreadNum"),
        "userStatus": d.get("userStatus"),
        "bindTapFlag": d.get("bindTapFlag"),
        "raw": data,
    }


def build_edit_password_request(
    open_id: str,
    open_token: str,
    old_password: str,
    new_password: str,
    verify_code: str | None = None,
    timestamp: int | None = None,
) -> bytes:
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    old_md5 = md5_hex(old_password)
    new_md5 = md5_hex(new_password)
    extra = {
        "apcId": str(APC_ID),
        "oldPassword": old_md5,
        "newPassword": new_md5,
    }
    if verify_code:
        extra["verifyCode"] = verify_code
    sign = generate_sign(
        msg_type=271,
        timestamp=timestamp,
        open_id=open_id,
        open_token=open_token,
        extra=extra,
        include_apc_id=False,
    )
    func_msg = json.dumps(
        {
            "apcId": APC_ID,
            "verifyCode": verify_code,
            "oldPassword": old_md5,
            "newPassword": new_md5,
        },
        separators=(",", ":"),
    )
    out = bytearray()
    out += _f_int(1, 271)
    out += _f_str(2, APP_ID)
    out += _f_str(3, APP_VERSION)
    out += _f_str(4, REUNION_SDK_VERSION)
    out += _f_str(5, CHANNEL_SDK_VERSION)
    out += _f_int(6, CHANNEL_ID)
    out += _f_str(7, str(SECONDARY_CHANNEL_ID))
    out += _f_str(8, open_id)
    out += _f_str(9, open_token)
    out += _f_str(10, PCK_NAME)
    out += _f_int(11, timestamp)
    out += _f_int(12, CP_CHANNEL_ID)
    out += _f_str(13, sign)
    out += _f_msg(14, build_base_msg())
    out += _f_str(15, func_msg)
    out += _f_str(16, PCK_SIGNATURE)
    out += _f_int(17, 0)
    return bytes(out)


def gaia_edit_password(
    open_id: str,
    open_token: str,
    old_password: str,
    new_password: str,
    verify_code: str | None = None,
    proxy: str | None = None,
) -> dict:
    body = build_edit_password_request(open_id, open_token, old_password, new_password, verify_code)
    data = post_gaia(body, proxy=proxy)
    ret = data.get("ret", data.get("code"))
    if ret not in (0, 1000, None):
        raise RuntimeError(f"修改密码失败 ret={ret} msg={data.get('msg', data)}")
    return {"ret": ret, "raw": data}


def build_send_update_pwd_code_request(
    open_id: str,
    open_token: str,
    mobile: str,
    verify_type: int = 5,
    timestamp: int | None = None,
) -> bytes:
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    sign = generate_sign(
        msg_type=6,
        timestamp=timestamp,
        open_id=open_id,
        open_token=open_token,
        extra={
            "apcId": str(APC_ID),
            "mobile": mobile,
            "verifyType": str(verify_type),
        },
        include_apc_id=False,
    )
    func_msg = json.dumps(
        {
            "verifyType": verify_type,
            "mobile": mobile,
            "apcId": APC_ID,
        },
        separators=(",", ":"),
    )
    out = bytearray()
    out += _f_int(1, 6)
    out += _f_str(2, APP_ID)
    out += _f_str(3, APP_VERSION)
    out += _f_str(4, REUNION_SDK_VERSION)
    out += _f_str(5, CHANNEL_SDK_VERSION)
    out += _f_int(6, CHANNEL_ID)
    out += _f_str(7, str(SECONDARY_CHANNEL_ID))
    out += _f_str(8, open_id)
    out += _f_str(9, open_token)
    out += _f_str(10, PCK_NAME)
    out += _f_int(11, timestamp)
    out += _f_int(12, CP_CHANNEL_ID)
    out += _f_str(13, sign)
    out += _f_msg(14, build_base_msg())
    out += _f_str(15, func_msg)
    out += _f_str(16, PCK_SIGNATURE)
    out += _f_int(17, 0)
    return bytes(out)


def gaia_send_update_pwd_code(
    open_id: str, open_token: str, mobile: str, proxy: str | None = None
) -> dict:
    body = build_send_update_pwd_code_request(open_id, open_token, mobile)
    data = post_gaia(body, proxy=proxy)
    ret = data.get("ret", data.get("code"))
    if ret not in (0, 1000, None):
        raise RuntimeError(f"发送验证码失败 ret={ret} msg={data.get('msg', data)}")
    return {"ret": ret, "raw": data}


def query_passport(
    user_name: str,
    password: str,
    token_required: bool = True,
    android_id: str | None = None,
    proxy: str | None = None,
) -> dict:
    """Full path: Gaia login -> LC token -> game session -> bag."""
    try:
        from scripts import bydsj_client
    except ImportError:
        import bydsj_client
    ITEMS, get_bag, token_login = (
        bydsj_client.ITEMS,
        bydsj_client.get_bag,
        bydsj_client.token_login,
    )

    login = gaia_login(user_name, password, proxy)
    auth = gaia_quick_auth(login["openId"], login["openToken"], proxy=proxy)
    lc_token = auth["authCode"] or ""
    if token_required and (not lc_token.startswith("LC_") or len(lc_token) != 35):
        raise RuntimeError(
            f"authCode is not an LC token: {lc_token!r} (len={len(lc_token)}) "
            f"login_raw={json.dumps(login['raw'], ensure_ascii=False)} auth_raw={json.dumps(auth['raw'], ensure_ascii=False)}"
        )
    session = token_login(lc_token, android_id, proxy)
    bag = get_bag(session["user_id"], session["token"], proxy)
    return {
        "account": user_name,
        "gaia_user": login["userName"],
        "nick_name": login["nickName"],
        "user_id": session["user_id"],
        "game_username": session["username"],
        "lc_token": lc_token,
        "money": session["money"],
        "diamond": session["diamond"],
        "items": {pid: bag.get(pid, 0) for pid, _ in ITEMS},
    }


def query_mobile_passport(
    mobile: str,
    password: str,
    token_required: bool = True,
    android_id: str | None = None,
    proxy: str | None = None,
) -> dict:
    """手机号账号完整查询：手机号登录 -> LC token -> 游戏会话 -> 背包。"""
    try:
        from scripts import bydsj_client
    except ImportError:
        import bydsj_client
    ITEMS, get_bag, token_login = (
        bydsj_client.ITEMS,
        bydsj_client.get_bag,
        bydsj_client.token_login,
    )

    login = gaia_mobile_pwd_login(mobile, password, proxy)
    auth = gaia_quick_auth(login["openId"], login["openToken"], proxy=proxy)
    lc_token = auth["authCode"] or ""
    if token_required and (not lc_token.startswith("LC_") or len(lc_token) != 35):
        raise RuntimeError(
            f"authCode is not an LC token: {lc_token!r} (len={len(lc_token)}) "
            f"login_raw={json.dumps(login['raw'], ensure_ascii=False)} auth_raw={json.dumps(auth['raw'], ensure_ascii=False)}"
        )
    session = token_login(lc_token, android_id, proxy)
    bag = get_bag(session["user_id"], session["token"], proxy)
    return {
        "account": mobile,
        "gaia_user": login["userName"],
        "nick_name": login["nickName"],
        "user_id": session["user_id"],
        "game_username": session["username"],
        "lc_token": lc_token,
        "money": session["money"],
        "diamond": session["diamond"],
        "items": {pid: bag.get(pid, 0) for pid, _ in ITEMS},
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        print("usage: python gaia_login.py <通行证账号> <密码>", file=sys.stderr)
        sys.exit(1)
    user, pwd = sys.argv[1], sys.argv[2]
    try:
        result = query_passport(user, pwd)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"通行证账号: {result['account']}  昵称: {result['nick_name']}  userID: {result['user_id']}")
    print(f"LC token: {result['lc_token']}")
    try:
        from scripts import bydsj_client
    except ImportError:
        import bydsj_client
    ITEMS = bydsj_client.ITEMS

    for pid, name in ITEMS:
        count = result["items"][pid]
        if pid == 10000:
            count = f"{result['money'] // 10000}亿"
        elif pid == 20000:
            count = result["diamond"]
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
