from scripts.bydsj_client import item_name


def test_item_name_known_id():
    assert item_name(10304) == "狂暴"
    assert item_name(10000) == "金币"
    assert item_name(31073) == "战魂宝箱"


def test_item_name_unknown_id_fallback():
    assert item_name(999999) == "未知道具(999999)"
