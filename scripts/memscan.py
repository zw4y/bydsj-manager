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
NAMES = [
    "神灯",
    "锁定",
    "冰冻",
    "狂暴",
    "号角",
    "绿灵石",
    "金刚石",
    "紫晶石",
    "血精石",
    "原石精华",
    "战魂自选礼盒",
]


def adb(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout


def adb_text(*args):
    return adb(*args).decode("utf-8", errors="replace")


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def get_maps(pid):
    text = adb_text("shell", f"su -c 'cat /proc/{pid}/maps'")
    ranges = []
    for line in text.splitlines():
        m = re.match(
            r"([0-9a-f]+)-([0-9a-f]+)\s+([r-][w-][x-][ps])\s+([0-9a-f]+)\s+\S+\s+\d+\s+(.*)",
            line,
        )
        if not m:
            continue
        start, end, perms, _off, path = int(m.group(1), 16), int(m.group(2), 16), m.group(3), m.group(4), m.group(5).strip()
        ranges.append({"start": start, "end": end, "perms": perms, "path": path})
    return ranges


def utf16le_bytes(s):
    return s.encode("utf-16le")


def utf8_bytes(s):
    return s.encode("utf-8")


def read_range(pid, start, end):
    a0 = start & ~0xFFF
    a1 = (end + 0xFFF) & ~0xFFF
    skip = a0 // 4096
    count = (a1 - a0) // 4096
    cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null"
    data = adb("exec-out", "su", "-c", cmd)
    return a0, data


def find_all(data, needle):
    results = []
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        results.append(pos)
        pos += 1
    return results


def main():
    parser = argparse.ArgumentParser(description="Read game memory via /proc/pid/mem and scan item names.")
    parser.add_argument("--out", default=str(ROOT / "hits.json"))
    parser.add_argument("--all-ranges", action="store_true", help="scan all readable ranges, not just heap+il2cpp")
    args = parser.parse_args()

    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    print(f"game pid={pid}", file=sys.stderr)

    ranges = get_maps(pid)
    targets = []
    for r in ranges:
        if "r" not in r["perms"]:
            continue
        if args.all_ranges or not r["path"] or "libil2cpp.so" in r["path"] or "global-metadata" in r["path"]:
            targets.append(r)
    print(f"target ranges: {len(targets)} (total readable: {len(ranges)})", file=sys.stderr)

    patterns = []
    for name in NAMES:
        patterns.append({"name": name, "encoding": "utf8", "bytes": utf8_bytes(name)})
        patterns.append({"name": name, "encoding": "utf16", "bytes": utf16le_bytes(name)})

    hits = []
    total_bytes = 0
    t0 = time.time()
    for i, r in enumerate(targets, 1):
        a0, data = read_range(pid, r["start"], r["end"])
        total_bytes += len(data)
        if len(data) < (r["end"] - r["start"]):
            pass
        for p in patterns:
            for pos in find_all(data, p["bytes"]):
                ctx_start = max(0, pos - 256)
                ctx_end = min(len(data), pos + len(p["bytes"]) + 256)
                hits.append(
                    {
                        "name": p["name"],
                        "encoding": p["encoding"],
                        "address": hex(a0 + pos),
                        "rangeStart": hex(r["start"]),
                        "rangeEnd": hex(r["end"]),
                        "perms": r["perms"],
                        "path": r["path"],
                        "contextHex": data[ctx_start:ctx_end].hex(),
                    }
                )
        if i % 10 == 0:
            elapsed = time.time() - t0
            print(
                f"progress: {i}/{len(targets)} ranges, {total_bytes/1024/1024:.1f} MB, "
                f"{len(hits)} hits, {elapsed:.1f}s",
                file=sys.stderr,
            )

    elapsed = time.time() - t0
    result = {
        "pid": pid,
        "scannedBytes": total_bytes,
        "elapsedSec": round(elapsed, 1),
        "ranges": len(targets),
        "hits": hits,
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    by_name = {}
    for h in hits:
        by_name.setdefault(h["name"], []).append(h)
    print("=== summary ===")
    for name, hs in by_name.items():
        encs = {}
        for h in hs:
            encs.setdefault(h["encoding"], []).append(h["address"])
        summary = ", ".join(f"{enc}: {len(addrs)} hits" for enc, addrs in encs.items())
        print(f"{name}: {summary}")
    print(f"saved {len(hits)} hits -> {args.out}")


if __name__ == "__main__":
    main()
