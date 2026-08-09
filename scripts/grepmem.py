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


def adb(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout


def adb_text(*args):
    return adb(*args).decode("utf-8", errors="replace")


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def get_readable_ranges(pid):
    text = adb_text("shell", f"su -c 'cat /proc/{pid}/maps'")
    ranges = []
    for line in text.splitlines():
        m = re.match(
            r"([0-9a-f]+)-([0-9a-f]+)\s+([r-][w-][x-][ps])\s+[0-9a-f]+\s+\S+\s+\d+\s+(.*)",
            line,
        )
        if m and "r" in m.group(3):
            path = m.group(4).strip()
            ranges.append(
                {
                    "start": int(m.group(1), 16),
                    "end": int(m.group(2), 16),
                    "perms": m.group(3),
                    "path": path,
                }
            )
    return ranges


def merge_ranges(ranges):
    ranges = sorted(ranges, key=lambda r: r["start"])
    merged = []
    for r in ranges:
        start, end = r["start"], r["end"]
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def read_window(pid, addr, before, after):
    start = (addr - before) & ~0xFFF
    end = (addr + after + 0xFFF) & ~0xFFF
    skip = start // 4096
    count = (end - start) // 4096
    cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null"
    data = adb("exec-out", "su", "-c", cmd)
    return start, data


def clean(chunk: bytes) -> str:
    text = chunk.decode("utf-8", errors="replace")
    text = text.replace("\r\r\n", " | ").replace("\r\n", " | ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return re.sub(r"\s+", " ", text)


def main():
    parser = argparse.ArgumentParser(description="Grep game memory on-device for ASCII patterns.")
    parser.add_argument("--pattern", action="append", required=True)
    parser.add_argument("--context", type=int, default=0, help="dump context bytes around each hit")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--include-file", action="store_true", help="also scan file-backed readable ranges")
    parser.add_argument("--min-size", type=lambda s: int(s, 0), default=0x100000)
    parser.add_argument("--include-ro", action="store_true", help="include read-only anonymous ranges")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    raw = get_readable_ranges(pid)
    if not args.include_file:
        raw = [r for r in raw if not r["path"]]
    if not args.include_ro:
        raw = [r for r in raw if "w" in r["perms"]]
    raw = [r for r in raw if r["end"] - r["start"] >= args.min_size]
    ranges = merge_ranges(raw)
    print(f"pid={pid}, merged readable ranges={len(ranges)}", file=sys.stderr)

    combined = "|".join(re.escape(p) for p in args.pattern)

    results = []
    t0 = time.time()
    for i, (rstart, rend) in enumerate(ranges, 1):
        a0 = rstart & ~0xFFF
        a1 = (rend + 0xFFF) & ~0xFFF
        skip = a0 // 4096
        count = (a1 - a0) // 4096
        inner = (
            f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null "
            f"| grep -aboE \"{combined}\""
        )
        out = adb_text("shell", f"su -c '{inner}'")
        for line in out.splitlines():
            m = re.match(r"^(\d+):(.+)$", line)
            if not m:
                continue
            offset = int(m.group(1))
            matched = m.group(2)
            addr = a0 + offset
            hit = {"pattern": matched, "address": hex(addr), "rangeStart": hex(rstart), "rangeEnd": hex(rend)}
            if args.context:
                base, data = read_window(pid, addr, args.context, args.context)
                rel = addr - base
                start = max(0, rel - args.context)
                end = min(len(data), rel + len(matched) + args.context)
                hit["context"] = clean(data[start:end])
            results.append(hit)
            if args.limit and len(results) >= args.limit:
                break
        if args.limit and len(results) >= args.limit:
            break
        if i % 50 == 0:
            print(f"progress: {i}/{len(ranges)} ranges, {len(results)} hits, {time.time()-t0:.0f}s", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {len(results)} hits -> {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        for h in results:
            print(h["address"], h["pattern"], h.get("context", "")[:300])
    print(f"done in {time.time()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
