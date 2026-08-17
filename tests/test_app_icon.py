"""app 图标定位逻辑测试（PyInstaller/Nuitka/开发模式兼容）。"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import _resolve_app_icon  # noqa: E402


def _make_icon(tmp_path, name="app_icon.ico"):
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    p = tmp_path / "assets" / name
    p.write_bytes(b"fake-ico")
    return p


def test_resolve_icon_dev_mode(monkeypatch, tmp_path):
    import app as app_mod

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    icon = _make_icon(tmp_path)
    monkeypatch.setattr(app_mod, "__file__", str(tmp_path / "app.py"))
    assert _resolve_app_icon() == icon


def test_resolve_icon_meipass_wins(monkeypatch, tmp_path):
    bundled = tmp_path / "bundle"
    _make_icon(bundled)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled), raising=False)
    assert _resolve_app_icon() == bundled / "assets" / "app_icon.ico"


def test_resolve_icon_frozen_exe_dir(monkeypatch, tmp_path):
    import app as app_mod

    exe_dir = tmp_path / "appdir"
    _make_icon(exe_dir)
    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "BydsjApp.exe"))
    monkeypatch.setattr(app_mod, "__file__", str(tmp_path / "nonexistent" / "app.py"))
    assert _resolve_app_icon() == exe_dir / "assets" / "app_icon.ico"


def test_resolve_icon_missing_returns_none(monkeypatch, tmp_path):
    import app as app_mod

    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(app_mod, "__file__", str(tmp_path / "app.py"))
    assert _resolve_app_icon() is None
