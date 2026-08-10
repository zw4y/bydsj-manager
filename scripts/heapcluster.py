import argparse
import json
import mmap
import struct
import sys
from pathlib import Path


def pack_value(value, enc):
    if enc == "i32":
        return struct.pack("<I", value)
    if enc == "i64":
        return struct.pack("<Q", value)
    if enc == "f32":
        return struct.pack("<f", float(value))
    if enc == "f64":
        return struct.pack("<d", float(value))
    raise ValueError(enc)


def find_all(mm, needle):
    pos = 0
    while True:
        pos = mm.find(needle, pos)
        if pos < 0:
            break
        yield pos
        pos += 1


def offset_to_addr(entries, off):
    for e in entries:
        if e["fileOffset"] <= off < e["fileOffset"] + e["length"]:
            return e["alignedStart"] + (off - e["fileOffset"])
    return None


def main():
    parser = argparse.ArgumentParser(description="Find memory regions containing many item count values.")
    parser.add_argument("--dump", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--counts", required=True)
    parser.add_argument("--window", type=int, default=4096)
    parser.add_argument("--min-distinct", type=int, default=7)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    counts = json.loads(Path(args.counts).read_text(encoding="utf-8"))
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    entries = index["entries"]
    values = [(name, v) for name, v in counts.items() if v > 0]
    print(f"values to search: {len(values)}", file=sys.stderr)

    encodings = ["i32", "i64", "f32", "f64"]
    with open(args.dump, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for enc in encodings:
            occ = []  # (addr, name, value)
            for name, value in values:
                needle = pack_value(value, enc)
                for off in find_all(mm, needle):
                    addr = offset_to_addr(entries, off)
                    if addr is not None:
                        occ.append((addr, name, value))
            occ.sort()
            print(f"=== encoding {enc}: {len(occ)} occurrences ===", file=sys.stderr)

            # sliding window to find clusters with many distinct names/values
            best = []
            i = 0
            while i < len(occ):
                j = i
                seen = {}
                while j < len(occ) and occ[j][0] - occ[i][0] < args.window:
                    seen[occ[j][1]] = occ[j][2]
                    j += 1
                if len(seen) >= args.min_distinct:
                    best.append((occ[i][0], occ[j - 1][0], len(seen), dict(seen)))
                i += 1

            # merge overlapping windows, keep the ones with most distinct values
            best.sort(key=lambda x: (-x[2], x[0]))
            merged = []
            for b in best:
                if not merged or b[0] > merged[-1][1] + 0x100:
                    merged.append(b)
                elif b[2] > merged[-1][2]:
                    merged[-1] = b
            sys.stdout.reconfigure(encoding="utf-8")
            print(f"\n##### {enc} clusters (top {args.top}) #####")
            for addr_start, addr_end, n, seen in merged[: args.top]:
                print(f"range {hex(addr_start)} - {hex(addr_end)} distinct={n}")
                for name, v in seen.items():
                    print(f"    {name} = {v}")
            print()


if __name__ == "__main__":
    main()
