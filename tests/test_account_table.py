"""账号表格勾选列整列点击命中的回归测试。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from app import AccountTable


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _click(table, x, y):
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    table.mousePressEvent(event)


def _make_table():
    table = AccountTable(3, 10)
    for row in range(3):
        table.setItem(row, 1, QTableWidgetItem())
        table.setItem(row, 2, QTableWidgetItem("acct"))
    table.setColumnWidth(0, 40)
    table.setColumnWidth(1, 50)
    table.setColumnWidth(2, 120)
    table.resize(600, 200)
    table.show()
    return table


def test_click_blank_area_in_check_column_toggles(qapp):
    table = _make_table()
    item = table.item(0, 1)
    assert item.checkState() == Qt.Unchecked

    _click(table, 60, 15)  # 勾选列（40~90）内的空白区域
    assert item.checkState() == Qt.Checked

    _click(table, 75, 15)  # 再次点击取消
    assert item.checkState() == Qt.Unchecked


def test_click_other_column_does_not_toggle(qapp):
    table = _make_table()
    item = table.item(0, 1)

    _click(table, 120, 15)  # 第 3 列
    assert item.checkState() == Qt.Unchecked
