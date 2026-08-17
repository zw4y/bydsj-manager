"""金币存取后本地更新测试：仓库用接口返回值，背包按差额推算，刷新不回归。"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import MainWindow  # noqa: E402
from scripts.card_auth import derive_key  # noqa: E402
from scripts.local_store import LocalAccountStore  # noqa: E402


def _make_window():
    appdata = tempfile.mkdtemp(prefix="bydsj_gold_")
    os.environ["APPDATA"] = appdata
    store = LocalAccountStore(
        str(Path(appdata) / "smoke.db"),
        derive_key("smoke", "smoke", b"smoke"),
    )
    QApplication.instance() or QApplication([])
    win = MainWindow(store, "smoke")
    return win


def _result(account="acc1", money=817676845, repo_gold=600000):
    return {
        "account": account,
        "money": money,
        "items": {},
        "repo": {10000: repo_gold},
        "nickname": "",
        "user_id": 1,
        "mobile": "",
        "device_code": "",
        "total_infull_num": 0,
        "cannon": 0,
    }


def _ctx(win, prop_id=10000, direction=1, current_num=100000, remaining=817676845):
    return {
        "account": {"account": "acc1"},
        "prop_id": prop_id,
        "prop_name": "金币",
        "direction": direction,
        "unit": "亿",
        "remaining_raw": remaining,
        "per_op_max": 999,
        "trusted": True,
        "session": {},
        "proxy": None,
        "total_done": 0,
        "gold_base": win._bag_qty.get(10000, 0),
        "current_num": current_num,
    }


def test_gold_deal_done_updates_locally(monkeypatch):
    win = _make_window()
    win._bag_qty[10000] = 817676845
    win._warehouse_qty[10000] = 500000
    win._deal_ctx = _ctx(win, current_num=100000)  # 存入 10 亿 → raw 100000
    win._on_deal_done({"result": 0, "leftRepoNum": 600000})

    assert win._bag_qty[10000] == 817576845  # 817676845 - 100000
    assert win._warehouse_qty[10000] == 600000  # 接口返回值
    assert win._pending_gold_adjust == 100000
    assert win._pending_gold_adjust_account == "acc1"
    assert win._deal_ctx["total_done"] == 1
    assert win._deal_ctx["remaining_raw"] == 817576845


def test_refresh_applies_pending_gold_adjust(monkeypatch):
    win = _make_window()
    win._pending_gold_adjust = 100000
    win._pending_gold_adjust_account = "acc1"
    win._pending_gold_adjust_base = 817676845
    win._apply_refresh_result(_result(money=817676845, repo_gold=600000))

    assert win._bag_qty[10000] == 817576845
    assert win._warehouse_qty[10000] == 600000
    assert win._pending_gold_adjust == 0
    assert win._pending_gold_adjust_account == ""


def test_refresh_skips_adjust_when_money_fresh(monkeypatch):
    """强制登录刷新拿到权威最新金币时，不叠加差额（避免重复计算）。"""
    win = _make_window()
    win._pending_gold_adjust = 100000
    win._pending_gold_adjust_account = "acc1"
    win._pending_gold_adjust_base = 817676845
    win._apply_refresh_result(_result(money=817576845, repo_gold=600000))

    assert win._bag_qty[10000] == 817576845  # 权威值，不再减 100000
    assert win._pending_gold_adjust == 0


def test_gold_withdraw_increases_bag(monkeypatch):
    win = _make_window()
    win._bag_qty[10000] = 817676845
    win._deal_ctx = _ctx(win, current_num=-50000)  # 取出 5 亿 → raw -50000
    win._on_deal_done({"result": 0, "leftRepoNum": 300000})

    assert win._bag_qty[10000] == 817726845
    assert win._warehouse_qty[10000] == 300000


def test_deal_failed_incomplete_read_warns(monkeypatch):
    win = _make_window()
    win._deal_ctx = _ctx(win, prop_id=10301, current_num=1, remaining=10)
    dialogs = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: dialogs.append(a))
    win._on_deal_failed("IncompleteRead(16 bytes read)")
    assert win._deal_dialog is None
    assert any("结果不确定" in str(args[2]) for args in dialogs)
    assert "响应中断，本次存取结果不确定" in win.txt_log.toPlainText()


def test_deal_failed_normal_no_uncertain_warning(monkeypatch):
    win = _make_window()
    win._deal_ctx = _ctx(win, prop_id=10301, current_num=1, remaining=10)
    dialogs = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: dialogs.append(a))
    win._on_deal_failed("仓库操作响应过短")
    assert dialogs
    assert "结果不确定" not in str(dialogs[0][2])
    assert "响应中断" not in win.txt_log.toPlainText()
