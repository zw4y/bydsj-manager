"""updater 逻辑测试：备份路径 / 进程存活 / 目录可写 / 替换重试 / 结果日志。"""

import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import updater


def test_backup_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = updater.backup_path(r"C:\apps\BydsjApp.exe")
    assert path == str(tmp_path / "BydsjManager" / "backups" / "BydsjApp.exe.old")


def test_backup_path_keeps_exe_dir_clean(monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = updater.backup_path(str(tmp_path / "BydsjApp.exe"))
    assert str(tmp_path / "BydsjApp.exe.old") not in path
    assert path.endswith("BydsjApp.exe.old")


def test_process_alive_dead_pid():
    assert not updater.process_alive(0)
    assert not updater.process_alive(999_999_999)


def test_process_alive_live_pid():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    try:
        assert updater.process_alive(proc.pid)
        assert updater.wait_process_exit(0)  # 无 PID 视为已退出
    finally:
        proc.kill()
        proc.wait()
    assert not updater.process_alive(proc.pid)


def test_dir_writable(tmp_path):
    ok, err = updater.dir_writable(str(tmp_path))
    assert ok and not err
    ok, err = updater.dir_writable(str(tmp_path / "no_such_dir"))
    assert not ok and err


def test_replace_with_retry_success(tmp_path):
    target = tmp_path / "app.exe"
    target.write_bytes(b"old-bytes")
    new = tmp_path / "new.exe"
    new.write_bytes(b"MZ" + b"new-bytes")
    backup = str(tmp_path / "backup.old")

    ok, err = updater.replace_with_retry(
        str(target), str(new), backup, timeout=5
    )
    assert ok and not err
    assert target.read_bytes() == b"MZnew-bytes"
    assert Path(backup).read_bytes() == b"old-bytes"
    assert not new.exists()


def test_replace_with_retry_failure(monkeypatch, tmp_path):
    target = tmp_path / "app.exe"
    target.write_bytes(b"old")
    new = tmp_path / "new.exe"
    new.write_bytes(b"MZ" + b"new")

    def boom(*args, **kwargs):
        raise PermissionError(13, "locked by system")

    monkeypatch.setattr(os, "replace", boom)
    ok, err = updater.replace_with_retry(
        str(target), str(new), str(tmp_path / "b.old"), timeout=1.2
    )
    assert not ok
    assert err


def test_replace_with_retry_rejects_invalid_pe(tmp_path):
    target = tmp_path / "app.exe"
    target.write_bytes(b"old")
    new = tmp_path / "new.exe"
    new.write_bytes(b"not-an-exe")
    ok, err = updater.replace_with_retry(
        str(target), str(new), str(tmp_path / "b.old"), timeout=1
    )
    assert not ok
    assert "不是有效的 exe" in err
    assert target.read_bytes() == b"old"


def test_write_result(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    updater.write_result(r"C:\apps\BydsjApp.exe", False, "目录被拦截")
    text = updater.update_result_log_path().read_text(encoding="utf-8")
    assert "ok=0" in text
    assert "目录被拦截" in text
    assert "BydsjApp.exe" in text


def test_check_cfa_returns_int():
    assert isinstance(updater.check_cfa_enabled(), int)


def test_app_reports_recent_update_failure(monkeypatch):
    """主窗口启动后检测到 24 小时内更新失败 → 弹出手动方案。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    appdata = tempfile.mkdtemp(prefix="bydsj_uptest_")
    monkeypatch.setenv("APPDATA", appdata)

    from PySide6.QtWidgets import QApplication

    from app import MainWindow
    from scripts.card_auth import derive_key
    from scripts.local_store import LocalAccountStore

    log_file = (
        Path(appdata) / "BydsjManager" / "updates" / "update_result.log"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)
    when = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    log_file.write_text(
        f"[{when}] target=C:\\x\\BydsjApp.exe ok=0 "
        "detail=PermissionError；目标位于受保护目录\n",
        encoding="utf-8",
    )

    app = QApplication.instance() or QApplication([])
    store = LocalAccountStore(
        str(Path(appdata) / "smoke.db"),
        derive_key("smoke", "smoke", b"smoke"),
    )
    win = MainWindow(store, "smoke")
    shown = []

    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: shown.append(a)
    )
    win._report_last_update_failure()

    assert shown, "应弹出更新失败提示"
    assert any("上次更新未成功" in str(args[1]) for args in shown)
