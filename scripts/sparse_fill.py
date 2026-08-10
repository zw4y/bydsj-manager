import argparse
import json
import subprocess
import sys
import time
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
    parser = argparse.ArgumentParser(description="Fill unreadable holes in a heap dump with per-page fallback.")
    parser.add_argument("--out", required=True, help="output prefix; reads <out>.bin and <out>.index.json, patches both")
    parser.add_argument("--chunk-size", type=lambda s: int(s, 0), default=0x10000)
    parser.add_argument("--per-page-timeout", type=float, default=5.0)
    args = parser.parse_args()

    bin_path = Path(args.out + ".bin")
    index_path = Path(args.out + ".index.json")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)

    entries = index["entries"]
    t0 = time.time()
    patched = 0
    with open(bin_path, "r+b") as fh:
        for i, e in enumerate(entries):
            expected = ((e["end"] + 0xFFF) & ~0xFFF) - e["alignedStart"]
            got = e["length"]
            if got >= expected:
                continue
            pos = e["alignedStart"] + got
            end = e["alignedStart"] + expected
            rel_base = e["fileOffset"] - e["alignedStart"]
            while pos < end:
                chunk_end = min(pos + args.chunk_size, end)
                size = chunk_end - pos
                pages = (size + 4095) // 4096
                cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={pos // 4096} count={pages} 2>/dev/null"
                data = adb("exec-out", "su", "-c", cmd)
                if len(data) == size:
                    fh.seek(rel_base + pos)
                    fh.write(data)
                else:
                    # per-page fallback
                    p = pos
                    while p < chunk_end:
                        page_size = min(4096, chunk_end - p)
                        cmd2 = f"dd if=/proc/{pid}/mem bs=4096 skip={p // 4096} count=1 2>/dev/null"
                        try:
                            d2 = adb("exec-out", "su", "-c", cmd2)
                        except Exception:
                            d2 = b""
                        fh.seek(rel_base + p)
                        fh.write(d2[:page_size] if d2 else b"\x00" * page_size)
                        p += 4096
                pos = chunk_end
            e["length"] = expected
            patched += 1
            print(
                f"patched entry {i}: {hex(e['alignedStart'])} length -> {expected} "
                f"({time.time()-t0:.0f}s)",
                file=sys.stderr,
            )

    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"patched {patched} entries -> {bin_path} / {index_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
