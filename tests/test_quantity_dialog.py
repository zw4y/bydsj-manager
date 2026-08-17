"""连续模式存取数量对话框测试：确定/全部存取提交不关闭，完成才关闭。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QPushButton  # noqa: E402

from app import QuantityDialog  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _button(dlg, text):
    for btn in dlg.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    return None


def _capture(dlg):
    captured = []
    dlg.submitted.connect(captured.append)
    return captured


def test_dialog_has_buttons():
    _app()
    dlg = QuantityDialog("输入数量（个）", 123456, "个")
    assert _button(dlg, "全部存取") is not None
    assert _button(dlg, "确定") is not None
    assert _button(dlg, "完成") is not None


def test_ok_submits_and_stays_open():
    _app()
    dlg = QuantityDialog("输入数量（个）", 123456, "个")
    captured = _capture(dlg)
    dlg.spin.setValue(100)
    _button(dlg, "确定").click()
    assert captured == [100]
    assert dlg.result() != QDialog.Accepted  # 弹窗保持打开
    assert dlg.spin.value() == 100  # 保留上次输入的数量


def test_all_submits_per_op_max():
    _app()
    dlg = QuantityDialog("输入数量（个）", 123456, "个", per_op_max=999)
    captured = _capture(dlg)
    _button(dlg, "全部存取").click()
    assert captured == [999]
    assert dlg.result() != QDialog.Accepted
    assert dlg.spin.value() == 999  # 保留上次输入的数量


def test_bullet_per_op_max_is_999():
    _app()
    dlg = QuantityDialog("输入数量（个）", 999, "个", available=1500, per_op_max=999)
    assert dlg.spin.maximum() == 999


def test_done_closes_dialog():
    _app()
    dlg = QuantityDialog("输入数量（个）", 123456, "个")
    _button(dlg, "完成").click()
    assert dlg.result() == QDialog.Accepted


def test_update_available_limits_spin():
    _app()
    dlg = QuantityDialog("输入数量（个）", 999, "个", available=9999, per_op_max=999)
    dlg.spin.setValue(999)
    dlg.update_available(500)
    assert "500" in dlg.lbl_available.text()
    assert dlg.spin.maximum() == 500
    assert dlg.spin.value() == 500  # 超出时自动钳制到剩余量
    dlg.update_available(1500)
    assert dlg.spin.maximum() == 999
    assert dlg.spin.value() == 500  # 保留上次值，不重置为 1
