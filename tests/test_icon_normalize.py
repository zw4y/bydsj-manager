import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from tools.normalize_item_icons import NAME_TO_PID, flood_trim, normalize_icon


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def test_name_to_pid_mapping_complete():
    assert len(NAME_TO_PID) == 17
    assert NAME_TO_PID["金币"] == 10000
    assert NAME_TO_PID["青铜弹头"] == 12003
    assert NAME_TO_PID["紫晶石"] == 10313
    assert NAME_TO_PID["战魂宝箱"] == 31073


def test_flood_trim_removes_background():
    _app()
    image = QImage(100, 100, QImage.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.fillRect(30, 30, 40, 40, QColor("red"))
    painter.end()
    trimmed = flood_trim(image)
    assert trimmed.width() == 40
    assert trimmed.height() == 40


def test_normalize_icon_returns_96_square():
    _app()
    image = QImage(120, 80, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.fillRect(20, 10, 60, 60, QColor("blue"))
    painter.end()
    canvas = normalize_icon(image)
    assert canvas.width() == 96
    assert canvas.height() == 96
    assert canvas.format() == QImage.Format_ARGB32
