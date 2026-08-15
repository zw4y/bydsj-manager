import re
import struct
import subprocess
import sys
from pathlib import Path

ADB = Path(r"E:\leidian\LDPlayer9\adb.exe")
PACKAGE = "com.shiyi.by3d"


def adb(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout


def adb_text(*args):
    return adb(*args).decode("utf-8", errors="replace")


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def get_maps(pid):
    text = adb_text("shell", f"cat /proc/{pid}/maps")
    maps = []
    for line in text.splitlines():
        m = re.match(r"([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+([0-9a-f]+)\s+\S+\s+\d+\s*(.*)", line)
        if m:
            maps.append(
                {
                    "start": int(m.group(1), 16),
                    "end": int(m.group(2), 16),
                    "perms": m.group(3),
                    "offset": int(m.group(4), 16),
                    "path": m.group(5),
                }
            )
    return maps


def find_libil2cpp_base(maps):
    best = None
    for mp in maps:
        if "libil2cpp.so" in mp["path"] and mp["perms"].startswith("r--") and mp["offset"] == 0:
            size = mp["end"] - mp["start"]
            if best is None or size > best[1]:
                best = (mp["start"], size)
    if best:
        return best[0]
    raise RuntimeError("libil2cpp.so mapping not found")


def read_bytes(pid, addr, size, chunk=0x10000):
    out = bytearray()
    pos = 0
    while pos < size:
        cur = min(chunk, size - pos)
        a0 = addr + pos
        page = a0 // 4096
        count = (cur + 4095) // 4096
        cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={page} count={count} 2>/dev/null"
        data = adb("exec-out", cmd)
        got = min(len(data), cur)
        out += data[:got]
        pos += cur
    return bytes(out)


def read_ptr(pid, addr):
    b = read_bytes(pid, addr, 8)
    return struct.unpack("<Q", b)[0]


def read_u32(pid, addr):
    b = read_bytes(pid, addr, 4)
    return struct.unpack("<I", b)[0]


def read_dotnet_string(pid, addr, max_len=4096):
    """Read an IL2CPP System.String (chars at +0x18, length at +0x10)."""
    if not addr:
        return None
    length = read_u32(pid, addr + 0x10)
    if length < 0 or length > max_len:
        return None
    raw = read_bytes(pid, addr + 0x18, length * 2)
    return raw.decode("utf-16-le", errors="replace")


def read_dotnet_byte_array(pid, addr, max_len=1 << 20):
    if not addr:
        return None
    length = read_u32(pid, addr + 0x18)
    if length < 0 or length > max_len:
        return None
    return read_bytes(pid, addr + 0x20, length)


def read_dotnet_string_array(pid, addr, max_len=1024):
    if not addr:
        return None
    length = read_u32(pid, addr + 0x18)
    if length < 0 or length > max_len:
        return None
    items = []
    for i in range(length):
        p = read_ptr(pid, addr + 0x20 + i * 8)
        items.append(p)
    return items


def main():
    pid = get_pid()
    if pid is None:
        print("game not running", file=sys.stderr)
        sys.exit(1)
    print(f"pid={pid}")
    maps = get_maps(pid)
    base = find_libil2cpp_base(maps)
    print(f"libil2cpp base=0x{base:x}")
    return pid, base


if __name__ == "__main__":
    main()
