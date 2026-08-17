"""空白行持久化 + 可勾选批量删除测试。"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import MainWindow  # noqa: E402
from scripts.card_auth import derive_key  # noqa: E402
from scripts.local_store import LocalAccountStore  # noqa: E402


def _make_window():
    appdata = tempfile.mkdtemp(prefix="bydsj_blank_")
    os.environ["APPDATA"] = appdata
    store = LocalAccountStore(
        str(Path(appdata) / "smoke.db"),
        derive_key("smoke", "smoke", b"smoke"),
    )
    QApplication.instance() or QApplication([])
    win = MainWindow(store, "smoke")
    return win, store


def _blank_row(win):
    for r in range(win.table_accounts.rowCount()):
        if not win.table_accounts.item(r, 2).text().strip():
            return r
    return -1


def test_insert_blank_row_persists_across_reload(monkeypatch):
    win, store = _make_window()
    win._insert_blank_row(0)
    assert len(store.list_accounts()) == 1
    win._reload_accounts()
    assert win.table_accounts.rowCount() == 1
    r = _blank_row(win)
    assert r == 0
    assert win.table_accounts.item(r, 0).data(Qt.UserRole) is not None
    assert win.table_accounts.item(r, 2).text() == ""
    assert win.table_accounts.item(r, 0).text() == "1"  # 序号保留


def test_blank_row_checkable(monkeypatch):
    win, store = _make_window()
    store.add_account("真实账号", "pwd", "", "passport")
    store.add_blank_row()
    win._reload_accounts()
    r = _blank_row(win)
    assert r >= 0
    win._loading_accounts = False
    win.table_accounts.item(r, 1).setCheckState(Qt.Checked)
    assert win.table_accounts.item(r, 1).checkState() == Qt.Checked
    assert win._last_checked_row == r


def test_batch_change_password_skips_blank_only(monkeypatch):
    win, store = _make_window()
    store.add_blank_row()
    win._reload_accounts()
    r = _blank_row(win)
    win._loading_accounts = False
    win.table_accounts.item(r, 1).setCheckState(Qt.Checked)
    prompts = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: prompts.append(a)
    )
    win._on_batch_change_password()
    assert prompts and "空白行" in str(prompts[0][2])


def test_delete_blank_row_removes_from_db(monkeypatch):
    win, store = _make_window()
    store.add_blank_row()
    win._reload_accounts()
    r = _blank_row(win)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.Yes
    )
    win._delete_row(r)
    assert store.list_accounts() == []
    assert win.table_accounts.rowCount() == 0
