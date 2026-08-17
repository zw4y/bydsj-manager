"""热更新替换工具：等待旧进程退出后，用新 exe 替换目标并重启。

v2 改进（解决朋友端更新失败后反复提示的问题）：
  1. 显式等待旧进程 PID 退出（最长 45 秒），避免旧 exe 被占用导致替换失败；
  2. 替换重试窗口从 ~30 秒延长到 ~60 秒，用 os.replace 原子替换（跨盘自动降级 copy）；
  3. 无论成功失败都会重新拉起目标 exe（失败时拉起的是未替换的旧版，应用不会“消失”）；
  4. 每次执行写入 %APPDATA%/BydsjManager/updates/update_result.log，失败带原因，
     并检测 Windows 受控文件夹访问/目标目录是否可写，供下次启动提示手动方案。
"""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STILL_ACTIVE = 259


def _appdata_dir() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home() / ".config"))


def backup_path(target: str) -> str:
    """旧版本备份路径：%APPDATA%/BydsjManager/backups/<exe名>.old。"""
    base = _appdata_dir()
    return str(base / "BydsjManager" / "backups" / (Path(target).name + ".old"))


def update_result_log_path() -> Path:
    return _appdata_dir() / "BydsjManager" / "updates" / "update_result.log"


def _hide_file(path: str) -> None:
    """Windows 下给备份文件加隐藏属性（非 Windows 忽略）。"""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)
        except Exception:  # noqa: BLE001
            pass


def process_alive(pid: int) -> bool:
    """判断进程是否仍存活（Windows 用 OpenProcess + STILL_ACTIVE）。"""
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(code)
                )
                return bool(ok) and code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_process_exit(pid: int, timeout: float = 45.0) -> bool:
    """等待指定 PID 退出；超时返回 False。"""
    if not pid or pid <= 0:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not process_alive(pid):
            return True
        time.sleep(1)
    return not process_alive(pid)


def dir_writable(path: str) -> tuple[bool, str]:
    """实测目标目录是否可写（可被权限/受控文件夹访问/杀软拦截）。"""
    try:
        fd, tmp = tempfile.mkstemp(dir=path, prefix=".bydsj_write_", suffix=".tmp")
        os.close(fd)
        os.remove(tmp)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def check_cfa_enabled() -> int:
    """读取 Windows 受控文件夹访问状态：0=关闭 1=阻止 2=仅审核。非 Windows 返回 0。"""
    if sys.platform != "win32":
        return 0
    import winreg

    candidates = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard\Controlled Folder Access",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard\Controlled Folder Access",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\Windows Defender\Windows Defender Exploit Guard\Controlled Folder Access",
        ),
    ]
    for hive, path in candidates:
        try:
            with winreg.OpenKey(hive, path) as key:
                value, _ = winreg.QueryValueEx(key, "EnableControlledFolderAccess")
                return int(value)
        except OSError:
            continue
    return 0


def protected_folder_paths() -> list[Path]:
    """用户 Shell 文件夹中的受控文件夹访问默认保护目录（桌面/文档/图片/视频/音乐）。"""
    paths: list[Path] = []
    if sys.platform != "win32":
        return paths
    try:
        import winreg

        names = {
            "Desktop": "Desktop",
            "Personal": "Documents",
            "My Pictures": "Pictures",
            "My Video": "Videos",
            "My Music": "Music",
        }
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            for reg_name, label in names.items():
                try:
                    value, _ = winreg.QueryValueEx(key, reg_name)
                    expanded = os.path.expandvars(value)
                    paths.append(Path(expanded).resolve())
                except OSError:
                    continue
    except Exception:  # noqa: BLE001
        pass
    return paths


def target_under_protected_folder(target: str) -> bool:
    target_resolved = Path(target).resolve()
    for folder in protected_folder_paths():
        try:
            target_resolved.relative_to(folder)
            return True
        except ValueError:
            continue
    return False


def replace_with_retry(
    target: str, new: str, backup: str, timeout: float = 60.0
) -> tuple[bool, str]:
    """带重试的替换：备份旧版 → os.replace 原子替换（跨盘降级 copy）。"""
    # 前置校验：新版本必须是有效的 PE 可执行文件，避免替换成损坏文件
    try:
        with open(new, "rb") as f:
            if f.read(2) != b"MZ":
                return False, f"新版本文件不是有效的 exe（{new}）"
    except OSError as exc:
        return False, f"无法读取新版本文件：{exc}"
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            if os.path.exists(target):
                if os.path.exists(backup):
                    os.remove(backup)
                shutil.copy2(target, backup)
                _hide_file(backup)
            try:
                os.replace(new, target)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 17:  # ERROR_NOT_SAME_DEVICE
                    shutil.copy2(new, target)
                    os.remove(new)
                else:
                    raise
            return True, ""
        except OSError as exc:
            last_error = repr(exc)
            time.sleep(1)
    return False, last_error


def write_result(target: str, ok: bool, detail: str) -> None:
    try:
        log_path = update_result_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"target={target} ok={1 if ok else 0} detail={detail}\n"
            )
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="要替换的 exe 路径")
    parser.add_argument("--new", required=True, help="下载好的新 exe 路径")
    parser.add_argument("--old-pid", type=int, default=0, help="旧应用进程 PID")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    new = os.path.abspath(args.new)
    backup = backup_path(target)
    Path(backup).parent.mkdir(parents=True, exist_ok=True)

    # 清理历史版本遗留的“exe 旁 .old”（旧 updater 产物），保持软件目录干净
    legacy = target + ".old"
    if os.path.exists(legacy):
        try:
            os.remove(legacy)
        except OSError:
            pass

    # 阶段 1：等旧进程退出（最长 45 秒）
    if not wait_process_exit(args.old_pid):
        write_result(target, False, f"旧进程 {args.old_pid} 45 秒内未退出")

    # 阶段 2：替换（最长 60 秒）
    replaced, error = replace_with_retry(target, new, backup)
    if replaced:
        write_result(target, True, "替换成功")
        try:
            os.remove(new)
        except OSError:
            pass
    else:
        writable, write_err = dir_writable(str(Path(target).parent))
        cfa = check_cfa_enabled()
        protected = target_under_protected_folder(target)
        hints = []
        if not writable:
            hints.append(f"目标目录不可写({write_err})")
        if cfa == 1:
            hints.append("Windows受控文件夹访问已开启(阻止)")
        if cfa == 2:
            hints.append("Windows受控文件夹访问为审核模式")
        if protected:
            hints.append("目标位于受保护目录(桌面/文档/图片/视频/音乐)")
        detail = error or "替换失败"
        if hints:
            detail += "；" + "；".join(hints)
        write_result(target, False, detail)

    # 阶段 3：无论成败都重新拉起目标（失败时拉起的是旧版，应用不会消失）
    try:
        subprocess.Popen(
            [target],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
