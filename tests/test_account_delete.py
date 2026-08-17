"""批量删除勾选行测试：只删除当前勾选的行，未勾选时退回单行删除。"""

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
    appdata = tempfile.mkdtemp(prefix="bydsj_del_")
    os.environ["APPDATA"] = appdata
    store = LocalAccountStore(
        str(Path(appdata) / "smoke.db"),
        derive_key("smoke", "smoke", b"smoke"),
    )
    QApplication.instance() or QApplication([])
    win = MainWindow(store, "smoke")
    return win, store


def _add_accounts(store, names):
    for i, name in enumerate(names):
        store.add_account(
            account=name,
            password=f"pwd{i}",
            secondary_password="",
            login_type="passport",
            sort_order=i,
        )


def _check_row(win, row):
    win._loading_accounts = True
    win.table_accounts.item(row, 1).setCheckState(Qt.Checked)
    win._loading_accounts = False


def test_delete_checked_rows_only(monkeypatch):
    win, store = _make_window()
    _add_accounts(store, ["账号A", "账号B", "账号C"])
    win._reload_accounts()
    assert win.table_accounts.rowCount() == 3

    # 勾选第 1、3 行（0 和 2），右键落在未勾选的第 2 行（1）
    _check_row(win, 0)
    _check_row(win, 2)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    win._delete_checked_rows(1)

    assert win.table_accounts.rowCount() == 1
    assert win.table_accounts.item(0, 2).text() == "账号B"
    remaining = [a["account"] for a in store.list_accounts()]
    assert remaining == ["账号B"]
    assert win._last_checked_row == -1


def test_delete_checked_rows_cancel(monkeypatch):
    win, store = _make_window()
    _add_accounts(store, ["账号A", "账号B"])
    win._reload_accounts()
    _check_row(win, 0)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No)
    )
    win._delete_checked_rows(0)
    assert win.table_accounts.rowCount() == 2
    assert len(store.list_accounts()) == 2


def test_delete_checked_rows_fallback_to_single(monkeypatch):
    win, store = _make_window()
    _add_accounts(store, ["账号A", "账号B"])
    win._reload_accounts()
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    # 没有任何勾选 → 退回删除右键行
    win._delete_checked_rows(1)
    assert win.table_accounts.rowCount() == 1
    assert win.table_accounts.item(0, 2).text() == "账号A"
    assert [a["account"] for a in store.list_accounts()] == ["账号A"]
