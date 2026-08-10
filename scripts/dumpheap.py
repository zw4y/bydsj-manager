import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADB = Path(r"E:\leidian\LDPlayer9\adb.exe")
PACKAGE = "com.shiyi.by3d"


def adb_text(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout.decode("utf-8", errors="replace")


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def get_ranges(pid, mode):
    text = adb_text("shell", f"su -c 'cat /proc/{pid}/maps'")
    ranges = []
    for line in text.splitlines():
        m = re.match(
            r"([0-9a-f]+)-([0-9a-f]+)\s+([r-][w-][x-][ps])\s+[0-9a-f]+\s+\S+\s+\d+\s+(.*)",
            line,
        )
        if not m:
            continue
        perms, path = m.group(3), m.group(4).strip()
        if mode == "rw-all":
            ok = "r" in perms and "w" in perms
        elif mode == "rw-p":
            ok = "r" in perms and "w" in perms and "s" not in perms and "x" not in perms
        elif mode == "rw-anon":
            ok = "r" in perms and "w" in perms and not path
        elif mode == "ro-anon":
            ok = "r" in perms and "w" not in perms and not path
        else:
            ok = False
        if ok:
            ranges.append((int(m.group(1), 16), int(m.group(2), 16)))
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def main():
    parser = argparse.ArgumentParser(description="Dump writable anonymous heap of the game process.")
    parser.add_argument("--out", required=True, help="output prefix; writes <out>.bin and <out>.index.json")
    parser.add_argument("--chunk-size", type=lambda s: int(s, 0), default=0x1000000, help="read chunk size (default 16MB)")
    parser.add_argument("--chunk-timeout", type=float, default=15.0, help="per-chunk adb read timeout")
    parser.add_argument("--mode", choices=["rw-all", "rw-p", "rw-anon", "ro-anon"], default="rw-anon")
    args = parser.parse_args()

    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    ranges = get_ranges(pid, args.mode)
    total = sum(end - start for start, end in ranges)
    print(f"pid={pid}, mode={args.mode}, ranges={len(ranges)}, total={total/1024/1024:.1f} MB", file=sys.stderr)

    bin_path = Path(args.out + ".bin")
    index_path = Path(args.out + ".index.json")
    entries = []
    written = 0
    t0 = time.time()
    with open(bin_path, "wb") as fh:
        for i, (start, end) in enumerate(ranges, 1):
            a0 = start & ~0xFFF
            a1 = (end + 0xFFF) & ~0xFFF
            offset = fh.tell()
            pos = a0
            while pos < a1:
                cur = min(args.chunk_size, a1 - pos)
                skip = pos // 4096
                count = cur // 4096
                cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null"
                try:
                    subprocess.run(
                        [str(ADB), "exec-out", "su", "-c", cmd],
                        stdout=fh,
                        timeout=args.chunk_timeout,
                    )
                except subprocess.TimeoutExpired:
                    print(
                        f"range {i} chunk at {hex(pos)} timed out after {args.chunk_timeout}s, continuing",
                        file=sys.stderr,
                    )
                pos += cur
            length = fh.tell() - offset
            entries.append(
                {
                    "start": start,
                    "end": end,
                    "alignedStart": a0,
                    "fileOffset": offset,
                    "length": length,
                }
            )
            written = fh.tell()
            if i % 20 == 0 or i == len(ranges):
                print(
                    f"progress: {i}/{len(ranges)} ranges, written {fh.tell()/1024/1024:.1f} MB, "
                    f"{time.time()-t0:.0f}s",
                    file=sys.stderr,
                )

    index_path.write_text(json.dumps({"pid": pid, "entries": entries}, indent=2), encoding="utf-8")
    print(f"saved {written} bytes -> {bin_path} (+ index)", file=sys.stderr)


if __name__ == "__main__":
    main()
