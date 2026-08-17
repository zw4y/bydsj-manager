"""一键打包：updater.exe + 用户端 BydsjApp.exe + 管理端 BydsjAdmin.exe。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run_pyinstaller(args: list[str]) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", *args]
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_nuitka(args: list[str]) -> None:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--standalone",
        "--windows-console-mode=disable",
        "--enable-plugin=pyside6",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--experimental=force-dependencies-pefile",
        *args,
    ]
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def build_nuitka_app() -> None:
    DIST.mkdir(exist_ok=True)
    run_nuitka(
        [
            f"--output-dir={DIST / 'nuitka_build'}",
            "--output-filename=BydsjApp.exe",
            f"--windows-icon-from-ico={ROOT / 'assets' / 'app_icon.ico'}",
            f"--include-data-file={ROOT / 'data' / 'flow5_template.bin'}=data/flow5_template.bin",
            f"--include-data-file={ROOT / 'data' / 'tokenlogin_template.bin'}=data/tokenlogin_template.bin",
            f"--include-data-dir={ROOT / 'assets'}=assets",
            f"--include-data-file={DIST / 'updater.exe'}=updater/updater.exe",
            "--nofollow-import-to=mitmproxy",
            "--nofollow-import-to=frida",
            "--nofollow-import-to=pytest",
            "--nofollow-import-to=paramiko",
            str(ROOT / "app.py"),
        ]
    )
    built = next(DIST.glob("nuitka_build/**/BydsjApp.exe"), None)
    if built is None:
        raise SystemExit("Nuitka 未生成 BydsjApp.exe")
    shutil.copy2(built, DIST / "BydsjApp.exe")
    print("Nuitka 用户端完成：", DIST / "BydsjApp.exe")


def main() -> None:
    user_app = "nuitka"
    if len(sys.argv) > 1 and sys.argv[1] == "--user-app":
        if len(sys.argv) < 3 or sys.argv[2] not in ("nuitka", "pyinstaller"):
            raise SystemExit("用法：python packaging/build.py [--user-app nuitka|pyinstaller]")
        user_app = sys.argv[2]

    DIST.mkdir(exist_ok=True)

    # 1) updater（用户端内嵌）
    run_pyinstaller(
        [
            "--onefile",
            "--noconsole",
            "--name",
            "updater",
            str(ROOT / "updater.py"),
        ]
    )

    # 2) 用户端（默认 Nuitka，可回退 PyInstaller）
    if user_app == "nuitka":
        build_nuitka_app()
    else:
        run_pyinstaller(
            [
                "--onefile",
                "--windowed",
                "--name",
                "BydsjApp",
                "--icon",
                str(ROOT / "assets" / "app_icon.ico"),
                "--add-data",
                f"{ROOT / 'data' / 'flow5_template.bin'};data",
                "--add-data",
                f"{ROOT / 'data' / 'tokenlogin_template.bin'};data",
                "--add-data",
                f"{ROOT / 'assets' / 'items'};assets/items",
                "--add-data",
                f"{ROOT / 'assets' / 'app_icon.ico'};assets",
                "--add-binary",
                f"{DIST / 'updater.exe'};updater",
                "--exclude-module",
                "mitmproxy",
                "--exclude-module",
                "frida",
                "--exclude-module",
                "pytest",
                "--exclude-module",
                "paramiko",
                str(ROOT / "app.py"),
            ]
        )

    # 3) 管理端
    run_pyinstaller(
        [
            "--onefile",
            "--windowed",
            "--name",
            "BydsjAdmin",
            str(ROOT / "admin_app.py"),
        ]
    )

    print("打包完成：", DIST)


if __name__ == "__main__":
    main()
