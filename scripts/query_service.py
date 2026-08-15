"""按账号特征自动选择大世界或通行证登录并查询。"""

from scripts import bydsj_client, gaia_login


def is_phone_account(account: str) -> bool:
    """判断是否为 11 位手机号（1 开头），通行证支持手机号 + 密码登录。"""
    return gaia_login.is_mobile_account(account)


def login_type_of(account: str) -> str:
    first = account[0]
    if (first.isascii() and first.isalpha()) or is_phone_account(account):
        return "passport"
    return "dashijie"


def query_account(account: str, password: str) -> dict:
    if login_type_of(account) == "passport":
        if is_phone_account(account):
            return gaia_login.query_mobile_passport(account, password)
        return gaia_login.query_passport(account, password)
    return bydsj_client.query(account, password)
