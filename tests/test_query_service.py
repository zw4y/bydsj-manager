from scripts import query_service


def test_passport_route_for_ascii_first_char(monkeypatch):
    calls = []

    def fake_passport(account, password):
        calls.append(("passport", account, password))
        return {"account": account}

    monkeypatch.setattr(query_service.gaia_login, "query_passport", fake_passport)
    result = query_service.query_account("wzj1004232242", "zf6114")
    assert result == {"account": "wzj1004232242"}
    assert calls == [("passport", "wzj1004232242", "zf6114")]


def test_dashijie_route_for_chinese_first_char(monkeypatch):
    calls = []

    def fake_dashijie(account, password):
        calls.append(("dashijie", account, password))
        return {"account": account}

    monkeypatch.setattr(query_service.bydsj_client, "query", fake_dashijie)
    result = query_service.query_account("万亿不倒", "vbnh12")
    assert result == {"account": "万亿不倒"}
    assert calls == [("dashijie", "万亿不倒", "vbnh12")]


def test_passport_route_for_phone_number(monkeypatch):
    calls = []

    def fake_mobile_passport(account, password):
        calls.append(("passport", account, password))
        return {"account": account}

    monkeypatch.setattr(query_service.gaia_login, "query_mobile_passport", fake_mobile_passport)
    result = query_service.query_account("17520694780", "cc8456")
    assert result == {"account": "17520694780"}
    assert calls == [("passport", "17520694780", "cc8456")]


def test_phone_detection():
    assert query_service.is_phone_account("17520694780") is True
    assert query_service.is_phone_account("15586479511") is True
    assert query_service.is_phone_account("175206947801") is False
    assert query_service.is_phone_account("123456") is False
    assert query_service.is_phone_account("by881119") is False
