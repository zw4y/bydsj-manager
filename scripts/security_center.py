"""账号安全中心：查询/添加信任设备（设备码 = Android ID）。"""

from __future__ import annotations

import hashlib
import urllib.parse

import httpx

from scripts import bydsj_client, gaia_login, query_service

SAFETY_BASE = "https://lobby.bydsj3d.com/safety/"
CODE_TYPE_TRUST = 19
CODE_TYPE_CHANGE_PWD = 13


def get_session(
    account: str,
    password: str,
    android_id: str | None = None,
    proxy: str | None = None,
    require_device: bool = False,
) -> dict:
    """返回带 user_id/token/昵称/代理ID 等字段的会话，并附带 mobile（通行证账号有）。

    登录/刷新/改密默认不依赖真实设备码：账号未填设备码时直接用协议默认设备码登录拿
    会话，避免触发“未连接模拟器”弹窗；显式传入 android_id（账号已填设备码）时仍使用
    该设备码，供仓库存取信任设备使用。仅当 require_device=True 时才走模拟器/缓存解析。
    """
    from scripts import bydsj_client

    if android_id:
        device_code = android_id
    elif require_device:
        device_code = bydsj_client.resolve_android_id(None)
    else:
        device_code = bydsj_client.ANDROID_ID
    if query_service.login_type_of(account) == "passport":
        login = gaia_login.login_user(account, password, proxy)
        auth = gaia_login.gaia_quick_auth(
            login["openId"], login["openToken"], proxy=proxy
        )
        sess = bydsj_client.token_login(auth["authCode"], device_code, proxy)
        sess["mobile"] = login.get("mobile") or ""
        sess["account"] = account
    else:
        info = bydsj_client.login(account, password, device_code, proxy)
        sess = bydsj_client.get_token(info, proxy=proxy)
        sess["mobile"] = ""
        sess["account"] = account
    sess["device_code"] = device_code
    return sess


def build_security_url(session: dict, mac: str) -> str:
    params = {
        "userId": session["user_id"],
        "userToken": session["token"],
        "platform": 4,
        "mac": mac,
        "agentId": session.get("agent_id", 0),
        "actAgentId": session.get("act_agent_id", 0),
        "cAgentId": 10000046,
        "version": "6.02.10",
        "gameId": 33,
        "infullNum": session.get("total_infull_num", 0),
        "nickName": session.get("nickname", ""),
        "agentAccountBindFlag": 0,
        "lbGameId": 2,
    }
    return SAFETY_BASE + "safetyCenter.do?" + urllib.parse.urlencode(params)


def _client(proxy: str | None = None) -> httpx.Client:
    kwargs = {"trust_env": False, "verify": False, "timeout": 20}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


def check_trust(
    session: dict, mac: str | None = None, proxy: str | None = None
) -> dict:
    mac = mac or session.get("device_code") or ""
    with _client(proxy) as client:
        resp = client.post(
            SAFETY_BASE + "checkTrustMac.do",
            data={"userId": session["user_id"], "userToken": session["token"], "mac": mac},
        )
        resp.raise_for_status()
        return resp.json()


def send_trust_sms(
    session: dict, phone: str | None = None, proxy: str | None = None
) -> dict:
    phone = phone or session.get("mobile") or ""
    with _client(proxy) as client:
        resp = client.post(
            SAFETY_BASE + "sendMessageCode.do",
            data={
                "userId": session["user_id"],
                "userToken": session["token"],
                "codeType": CODE_TYPE_TRUST,
                "phone": phone,
            },
        )
        resp.raise_for_status()
        return resp.json()


def trust_device(
    session: dict,
    phone: str | None,
    mac: str | None,
    message_code: str,
    proxy: str | None = None,
) -> dict:
    phone = phone or session.get("mobile") or ""
    mac = mac or session.get("device_code") or ""
    with _client(proxy) as client:
        resp = client.post(
            SAFETY_BASE + "trustMac.do",
            data={
                "userId": session["user_id"],
                "userToken": session["token"],
                "mac": mac,
                "codeType": CODE_TYPE_TRUST,
                "messageCode": message_code,
                "phone": phone,
            },
        )
        resp.raise_for_status()
        return resp.json()


def send_change_pwd_sms(
    session: dict, phone: str, proxy: str | None = None
) -> dict:
    with _client(proxy) as client:
        resp = client.post(
            SAFETY_BASE + "sendMessageCode.do",
            data={
                "userId": session["user_id"],
                "userToken": session["token"],
                "codeType": CODE_TYPE_CHANGE_PWD,
                "phone": phone,
            },
        )
        resp.raise_for_status()
        return resp.json()


def change_password(
    session: dict,
    phone: str,
    message_code: str,
    new_password: str,
    proxy: str | None = None,
) -> dict:
    pwd_md5 = hashlib.md5(new_password.encode("utf-8")).hexdigest()
    with _client(proxy) as client:
        resp = client.post(
            SAFETY_BASE + "findp.do",
            data={
                "userId": session["user_id"],
                "userToken": session["token"],
                "password": pwd_md5,
                "confirmPassword": pwd_md5,
                "codeType": CODE_TYPE_CHANGE_PWD,
                "messageCode": message_code,
                "phone": phone,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultType") != 1:
            raise RuntimeError(data.get("errorMsg") or "修改密码失败")
        return data
