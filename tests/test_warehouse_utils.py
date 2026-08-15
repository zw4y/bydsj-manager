from scripts.warehouse import deal_max_display, display_to_deal_num, display_unit


def test_gold_display_to_deal_num():
    assert display_to_deal_num(10000, 1) == 10000
    assert display_to_deal_num(10000, 7445) == 74450000


def test_normal_item_display_to_deal_num():
    assert display_to_deal_num(10302, 5) == 5


def test_display_unit():
    assert display_unit(10000) == "亿"
    assert display_unit(10302) == "个"


def test_bullet_deal_max_caps_at_999():
    assert deal_max_display(12003, 500) == 500
    assert deal_max_display(12004, 1500) == 999
    assert deal_max_display(12006, 2000) == 999
    assert deal_max_display(12005, 100) == 100


def test_bullet_deal_max_applies_to_both_directions():
    # 存取方向只影响来源数量，上限都是 min(来源, 999)
    assert deal_max_display(12003, 1500) == 999
    assert deal_max_display(12003, 800) == 800


def test_normal_item_deal_max():
    assert deal_max_display(10302, 100) == 100


def test_gold_deal_max_uses_display_unit():
    assert deal_max_display(10000, 74450000) == 7445
