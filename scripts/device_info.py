"""从模拟器/设备读取游戏协议使用的设备码（Android ID）。

游戏协议里的设备码来自 Orion SDK 配置，通常是 16 位十六进制 Android ID，
不一定等于 `settings get secure android_id`。
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pyDes

DEFAULT_FALLBACK_ANDROID_ID = "157bc3df28f459f0"
GAIA_DES_KEY = b"gaia\x00\x00\x00\x00"
ORION_DES_KEY = b"orion\x00\x00\x00"
ORION_PREF_PATH = "/data/data/com.shiyi.by3d/shared_prefs/com.shiyi.by3d.orion.xml"

_cached_device_code: str | None = None
PROJECT_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "device_code.txt"


def _appdata_cache_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "BydsjManager" / "device_code.txt"


def _cache_paths() -> list[Path]:
    return [_appdata_cache_path(), PROJECT_CACHE_FILE]


def read_cached_device_code() -> str | None:
    for path in _cache_paths():
        try:
            code = path.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"[0-9a-fA-F]{16}", code):
                return code
        except Exception:
            continue
    return None


def save_device_code(code: str) -> None:
    code = code.lower()
    for path in _cache_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code + "\n", encoding="utf-8")
            return
        except Exception:
            continue


def find_adb() -> str | None:
    env = os.environ.get("BYDSJ_ADB") or os.environ.get("ADB_PATH")
    if env and Path(env).exists():
        return env
    found = shutil.which("adb")
    if found:
        return found
    candidates = [
        r"E:\leidian\LDPlayer9\adb.exe",
        r"D:\leidian\LDPlayer9\adb.exe",
        r"C:\leidian\LDPlayer9\adb.exe",
        r"C:\Program Files\LDPlayer9\adb.exe",
        r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def adb(*args: str) -> str:
    adb_path = find_adb()
    if not adb_path:
        raise RuntimeError("未找到 adb，请设置 BYDSJ_ADB 环境变量或手动提供设备码")
    result = subprocess.run([adb_path, *args], capture_output=True, timeout=20)
    return result.stdout.decode("utf-8", errors="replace")


def find_ldconsole() -> str | None:
    env = os.environ.get("BYDSJ_LDCONSOLE")
    if env and Path(env).exists():
        return env
    candidates = [
        r"E:\leidian\LDPlayer9\ldconsole.exe",
        r"D:\leidian\LDPlayer9\ldconsole.exe",
        r"C:\leidian\LDPlayer9\ldconsole.exe",
        r"C:\Program Files\LDPlayer9\ldconsole.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def adb_ready() -> bool:
    try:
        out = adb("devices")
        for line in out.splitlines()[1:]:
            if "emulator-" in line and "device" in line:
                return True
    except Exception:
        pass
    return False


def launch_ldplayer() -> bool:
    console = find_ldconsole()
    if not console:
        return False
    try:
        subprocess.run([console, "launch", "--index", "0"], timeout=30, capture_output=True)
        return True
    except Exception:
        return False


def wait_for_adb(timeout: float = 120) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if adb_ready():
            return True
        time.sleep(2)
    return False


def ensure_emulator() -> bool:
    if adb_ready():
        return True
    if launch_ldplayer():
        return wait_for_adb()
    return False


def _des_decrypt(raw: bytes, key: bytes) -> str | None:
    try:
        des = pyDes.des(key, pyDes.ECB, padmode=pyDes.PAD_PKCS5)
        return des.decrypt(raw).decode("utf-8", errors="replace")
    except Exception:
        return None


def decrypt_orion_value(value: str) -> str | None:
    """解密 Orion 共享参数：优先 JSON encVal（Gaia），再试 Orion 原始 DES 密文。"""
    try:
        payload = json.loads(value)
        if payload.get("encFlag") != 1:
            return value
        enc = payload.get("encVal", "")
        raw = base64.b64decode(enc)
        return _des_decrypt(raw, GAIA_DES_KEY)
    except Exception:
        pass
    try:
        raw = base64.b64decode(value)
        return _des_decrypt(raw, ORION_DES_KEY)
    except Exception:
        return None


def read_orion_xml() -> str:
    try:
        return adb("shell", f"su -c 'cat {ORION_PREF_PATH}'")
    except Exception:
        adb("root")
        adb("wait-for-device")
        return adb("shell", f"cat {ORION_PREF_PATH}")


def parse_orion_android_id(xml_text: str) -> str | None:
    """从 Orion XML 中逐个解密 string 值，找 androidId。"""
    for match in re.finditer(r"<string name=\"([^\"]+)\">([^<]+)</string>", xml_text):
        value = html.unescape(match.group(2))
        plain = decrypt_orion_value(value)
        if not plain:
            continue
        try:
            data = json.loads(plain)
        except Exception:
            continue
        for key in ("androidId", "android_id", "deviceId", "mac"):
            candidate = data.get(key)
            if isinstance(candidate, str) and re.fullmatch(r"[0-9a-fA-F]{16}", candidate):
                return candidate.lower()
    return None


def get_system_android_id() -> str | None:
    out = adb("shell", "settings get secure android_id").strip()
    return out if re.fullmatch(r"[0-9a-fA-F]{16}", out) else None


def get_device_code() -> str:
    """获取游戏协议设备码。优先级：环境变量 > Orion 配置 > 系统 Android ID。"""
    global _cached_device_code
    if _cached_device_code:
        return _cached_device_code
    env_code = os.environ.get("BYDSJ_DEVICE_CODE")
    if env_code and re.fullmatch(r"[0-9a-fA-F]{16}", env_code):
        _cached_device_code = env_code.lower()
        save_device_code(_cached_device_code)
        return _cached_device_code
    cached = read_cached_device_code()
    if cached:
        _cached_device_code = cached
        return _cached_device_code
    auto_launch = os.environ.get("BYDSJ_AUTO_LAUNCH_EMULATOR", "0") == "1"
    if auto_launch:
        if not ensure_emulator():
            raise RuntimeError("自动启动雷电模拟器失败，请手动打开模拟器或设置 BYDSJ_DEVICE_CODE。")
    elif not adb_ready():
        raise RuntimeError(
            "未连接模拟器。首次使用请手动打开模拟器一次；"
            "之后设备码会缓存在本机，不再需要模拟器。也可设置 BYDSJ_DEVICE_CODE 或 BYDSJ_AUTO_LAUNCH_EMULATOR=1。"
        )
    try:
        code = parse_orion_android_id(read_orion_xml())
        if code:
            _cached_device_code = code
            save_device_code(code)
            return code
    except Exception:
        pass
    try:
        code = get_system_android_id()
        if code:
            _cached_device_code = code
            save_device_code(code)
            return code
    except Exception:
        pass
    raise RuntimeError(
        "无法自动获取设备码：未连接模拟器或未找到 Orion 配置。"
        "可设置 BYDSJ_DEVICE_CODE 环境变量手动指定 16 位设备码。"
    )
