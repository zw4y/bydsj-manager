"""Gaia 手机号密码登录（msgType 291）的单元测试。"""

import hashlib
import json

from scripts import gaia_login


def _read_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _parse_fields(buf):
    fields = {}
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        no, wire = key >> 3, key & 7
        if wire == 0:
            val, pos = _read_varint(buf, pos)
            fields[no] = val
        elif wire == 2:
            ln, pos = _read_varint(buf, pos)
            fields[no] = buf[pos : pos + ln]
            pos += ln
        else:
            break
    return fields


def test_is_mobile_account():
    assert gaia_login.is_mobile_account("17520694780") is True
    assert gaia_login.is_mobile_account(" 15586479511 ") is True
    assert gaia_login.is_mobile_account("175206947801") is False
    assert gaia_login.is_mobile_account("wzj1004232242") is False


def test_build_mobile_pwd_login_request_structure():
    pwd_md5 = hashlib.md5("cc8456".encode("utf-8")).hexdigest()
    body = gaia_login.build_mobile_pwd_login_request("17520694780", pwd_md5)
    fields = _parse_fields(body)

    assert fields[1] == gaia_login.MSG_TYPE_MOBILE_PWD_LOGIN
    assert fields[2].decode() == gaia_login.APP_ID
    assert fields[8].decode() == ""
    assert fields[9].decode() == ""
    assert isinstance(fields[13], bytes) and len(fields[13]) == 32

    func = json.loads(fields[15].decode("utf-8"))
    assert set(func.keys()) == {"mobile", "password", "apcId"}
    assert func["mobile"] == "17520694780"
    assert func["password"] == pwd_md5
    assert func["apcId"] == gaia_login.APC_ID


def test_login_user_dispatches_mobile(monkeypatch):
    calls = []

    def fake_mobile(mobile, password, proxy=None):
        calls.append(("mobile", mobile, password))
        return {"via": "mobile"}

    def fake_account(user_name, password, proxy=None):
        calls.append(("account", user_name, password))
        return {"via": "account"}

    monkeypatch.setattr(gaia_login, "gaia_mobile_pwd_login", fake_mobile)
    monkeypatch.setattr(gaia_login, "gaia_login", fake_account)

    assert gaia_login.login_user("17520694780", "cc8456") == {"via": "mobile"}
    assert gaia_login.login_user("wzj1004232242", "zf6114") == {"via": "account"}
    assert calls == [
        ("mobile", "17520694780", "cc8456"),
        ("account", "wzj1004232242", "zf6114"),
    ]
