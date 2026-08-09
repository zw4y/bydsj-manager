import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADB = Path(r"E:\leidian\LDPlayer9\adb.exe")
PACKAGE = "com.shiyi.by3d"


def adb(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout


def adb_text(*args):
    return adb(*args).decode("utf-8", errors="replace")


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def main():
    parser = argparse.ArgumentParser(description="Dump a memory window from the game process.")
    parser.add_argument("--addr", required=True, help="start address, hex like 0x763843000000")
    parser.add_argument("--size", required=True, help="size in bytes, decimal or hex with 0x")
    parser.add_argument("--out", required=True, help="output file path")
    parser.add_argument("--chunk", default="0x100000", help="read chunk size (default 1MB)")
    args = parser.parse_args()

    addr = int(args.addr, 16)
    size = int(args.size, 0)
    chunk = int(args.chunk, 0)
    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    print(f"pid={pid}, dump {hex(addr)} + {size} bytes, chunk={hex(chunk)}", file=sys.stderr)

    buf = bytearray(size)
    filled = 0
    pos = 0
    while pos < size:
        cur = min(chunk, size - pos)
        a0 = addr + pos
        skip = a0 // 4096
        count = (cur + 4095) // 4096
        cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null"
        data = adb("exec-out", "su", "-c", cmd)
        got = min(len(data), cur)
        buf[pos : pos + got] = data[:got]
        filled += got
        pos += cur

    Path(args.out).write_bytes(buf)
    print(f"saved {filled}/{size} bytes -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
