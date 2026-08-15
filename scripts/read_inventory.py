import argparse
import json
import mmap
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADB = Path(r"E:\leidian\LDPlayer9\adb.exe")
PACKAGE = "com.shiyi.by3d"

ITEM_NAMES = {
    10300: "神灯",
    10301: "锁定",
    10302: "冰冻",
    10304: "狂暴",
    10305: "号角",
    10311: "绿灵石",
    10312: "金刚石",
    10313: "紫晶石",
    10314: "血精石",
    10315: "原石精华",
    31073: "战魂自选礼盒",
}

ANCHOR_IDS = [31073, 10300, 10301, 10302, 10304, 10311, 10312, 10313, 10314, 10315]


def adb_text(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout.decode("utf-8", errors="replace")


def adb(*args):
    return subprocess.run([str(ADB), *args], capture_output=True).stdout


def get_pid():
    out = adb_text("shell", f"pidof {PACKAGE}").strip()
    return int(out.split()[0]) if out else None


def get_libc_malloc_ranges(pid):
    text = adb_text("shell", f"su -c 'cat /proc/{pid}/maps'")
    ranges = []
    for line in text.splitlines():
        m = re.match(
            r"([0-9a-f]+)-([0-9a-f]+)\s+([r-][w-][x-][ps])\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*)",
            line,
        )
        if not m:
            continue
        perms, path = m.group(3), m.group(4).strip()
        if "r" in perms and "w" in perms and "libc_malloc" in path:
            ranges.append((int(m.group(1), 16), int(m.group(2), 16)))
    ranges.sort()
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def dump_ranges(pid, ranges, out_prefix):
    bin_path = Path(out_prefix + ".bin")
    index_path = Path(out_prefix + ".index.json")
    entries = []
    with open(bin_path, "wb") as fh:
        for i, (start, end) in enumerate(ranges, 1):
            a0 = start & ~0xFFF
            a1 = (end + 0xFFF) & ~0xFFF
            offset = fh.tell()
            pos = a0
            while pos < a1:
                cur = min(0x1000000, a1 - pos)
                skip = pos // 4096
                count = cur // 4096
                cmd = f"dd if=/proc/{pid}/mem bs=4096 skip={skip} count={count} 2>/dev/null"
                try:
                    subprocess.run(
                        [str(ADB), "exec-out", "su", "-c", cmd],
                        stdout=fh,
                        timeout=15,
                    )
                except subprocess.TimeoutExpired:
                    pass
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
    index_path.write_text(json.dumps({"pid": pid, "entries": entries}, indent=2), encoding="utf-8")
    return bin_path, index_path


def addr_of(entries, off):
    for e in entries:
        if e["fileOffset"] <= off < e["fileOffset"] + e["length"]:
            return e["alignedStart"] + (off - e["fileOffset"])
    return None


def find_pattern(mm, pattern, limit=100):
    out = []
    pos = 0
    while len(out) < limit:
        pos = mm.find(pattern, pos)
        if pos < 0:
            break
        out.append(pos)
        pos += 1
    return out


def decode_table(mm, entries, anchor_off):
    """Decode (id, count) pairs around an anchor id TValue."""
    base = max(0, anchor_off - 0x10000)
    end = min(len(mm), anchor_off + 0x30000)
    window = mm[base:end]
    pairs = {}
    pos = 0
    while True:
        p = window.find(b"\x13", pos)
        if p < 0 or p < 8:
            break
        cnt = struct.unpack_from("<q", window, p - 8)[0]
        if p - 0x28 >= 0:
            idv = struct.unpack_from("<q", window, p - 0x20 - 8)[0]
            idtag = window[p - 0x20]
            if idtag == 0x13 and 0 < idv < 200000 and 0 <= cnt < 100000000:
                pairs.setdefault((idv, cnt), base + (p - 8))
        pos = p + 1
    return pairs


def id_tvalue_ok(mm, pos):
    return pos >= 0 and pos + 8 < len(mm) and mm[pos + 8] == 0x13


def read_count_at(mm, pos):
    if pos + 0x30 > len(mm):
        return None
    cnt = struct.unpack_from("<q", mm, pos + 0x20)[0]
    if mm[pos + 0x28] != 0x13 or not (0 <= cnt < 100000000):
        return None
    return cnt


def find_chain_bases(mm, entries, ids, stride=0x80):
    """Find bases where each id TValue appears at base + i*stride."""
    first = ids[0]
    pattern = struct.pack("<q", first) + b"\x13"
    bases = []
    pos = 0
    while True:
        pos = mm.find(pattern, pos)
        if pos < 0:
            break
        ok = True
        for i, idv in enumerate(ids):
            p = pos + i * stride
            if not id_tvalue_ok(mm, p):
                ok = False
                break
            if struct.unpack_from("<q", mm, p)[0] != idv:
                ok = False
                break
        if ok:
            bases.append(pos)
        pos += 1
    return bases


def decode_around(mm, entries, base, span=0x30000):
    """Decode strict (id, count) pairs in a window around a table base."""
    start = max(0, base - span)
    end = min(len(mm), base + span)
    window = mm[start:end]
    pairs = {}
    pos = 0
    while True:
        p = window.find(b"\x13", pos)
        if p < 0 or p < 8:
            break
        cnt = struct.unpack_from("<q", window, p - 8)[0]
        if p - 0x28 >= 0:
            idv = struct.unpack_from("<q", window, p - 0x20 - 8)[0]
            idtag = window[p - 0x20]
            if idtag == 0x13 and 0 < idv < 200000 and 0 <= cnt < 100000000:
                pairs.setdefault((idv, cnt), start + (p - 8))
        pos = p + 1
    return pairs


def read_chain_counts(mm, base, ids, stride=0x80):
    """Read counts for ids at base + i*stride."""
    result = {}
    for i, idv in enumerate(ids):
        p = base + i * stride
        if not id_tvalue_ok(mm, p):
            continue
        if struct.unpack_from("<q", mm, p)[0] != idv:
            continue
        cnt = read_count_at(mm, p)
        if cnt is not None:
            result[idv] = cnt
    return result


def most_frequent(counts_by_id):
    out = {}
    for idv, counts in counts_by_id.items():
        freq = {}
        for c in counts:
            freq[c] = freq.get(c, 0) + 1
        out[idv] = max(freq, key=lambda c: freq[c])
    return out


def main():
    parser = argparse.ArgumentParser(description="Read fishing game inventory from game memory.")
    parser.add_argument("--out", default=str(ROOT / "inventory.json"))
    parser.add_argument("--tmp", default=str(ROOT / "dumps" / "inventory_tmp"))
    args = parser.parse_args()

    pid = get_pid()
    if pid is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    print(f"pid={pid}", file=sys.stderr)

    ranges = get_libc_malloc_ranges(pid)
    total = sum(e - s for s, e in ranges)
    print(f"libc_malloc ranges={len(ranges)}, total={total/1024/1024:.1f} MB", file=sys.stderr)
    t0 = time.time()
    bin_path, index_path = dump_ranges(pid, ranges, args.tmp)
    print(f"dump done in {time.time()-t0:.0f}s", file=sys.stderr)

    entries = json.loads(index_path.read_text(encoding="utf-8"))["entries"]
    with open(bin_path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        MAIN_CHAIN = [10300, 10301, 10302, 10304, 10311, 10312, 10313, 10314, 10315]
        BACKPACK_CHAIN = [10300, 10301, 10302]

        main_bases = find_chain_bases(mm, entries, MAIN_CHAIN)
        backpack_bases = find_chain_bases(mm, entries, BACKPACK_CHAIN)
        print(f"main chain bases: {len(main_bases)}, backpack chain bases: {len(backpack_bases)}", file=sys.stderr)
        for b in main_bases:
            print(f"  main base {hex(addr_of(entries, b))}: {read_chain_counts(mm, b, MAIN_CHAIN)}", file=sys.stderr)
        for b in backpack_bases:
            print(f"  backpack base {hex(addr_of(entries, b))}: {read_chain_counts(mm, b, BACKPACK_CHAIN)}", file=sys.stderr)

        main_counts = {}
        for base in main_bases:
            counts = read_chain_counts(mm, base, MAIN_CHAIN)
            for idv, cnt in counts.items():
                main_counts.setdefault(idv, []).append(cnt)

        backpack_counts = {}
        backpack_extra = {}
        for base in backpack_bases:
            pairs = decode_around(mm, entries, base)
            if (31073, 5) in pairs:
                counts = read_chain_counts(mm, base, BACKPACK_CHAIN)
                for idv, cnt in counts.items():
                    backpack_counts.setdefault(idv, []).append(cnt)
                for (idv, cnt), addr in pairs.items():
                    if idv == 31073:
                        backpack_extra.setdefault(idv, []).append(cnt)

        main_best = most_frequent(main_counts)
        backpack_best = most_frequent(backpack_counts)
        backpack_extra_best = most_frequent(backpack_extra)

        merged = dict(main_best)
        merged.update(backpack_best)       # backpack wins for 神灯/锁定/冰冻
        merged.update(backpack_extra_best) # 礼盒 etc. from backpack table

        # 号角: not reliably present in the verified tables; treat as 0 if absent
        if 10305 not in merged:
            merged[10305] = 0

        print(f"merged ids: {len(merged)}", file=sys.stderr)
        items = []
        for idv in sorted(ITEM_NAMES):
            if idv not in merged:
                continue
            cnt = merged[idv]
            items.append(
                {
                    "id": idv,
                    "name": ITEM_NAMES.get(idv),
                    "count": cnt,
                }
            )
        result = {
            "pid": pid,
            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
        }
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("=== inventory ===")
        for it in items:
            if it["name"]:
                print(f"  {it['name']}: {it['count']}  (id={it['id']})")
        print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
