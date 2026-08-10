import argparse
import json
import mmap
import struct
import sys
from pathlib import Path


def build_page_map(index_entries):
    """alignedStart -> (fileOffset, length) for each entry."""
    page_map = {}
    for e in index_entries:
        page_map[e["alignedStart"]] = (e["fileOffset"], e["length"])
    return page_map


def iterate_pages(before_map, after_map):
    addrs = set(before_map) | set(after_map)
    for addr in sorted(addrs):
        yield addr, before_map.get(addr), after_map.get(addr)


def read_page(mm, entry):
    file_off, length = entry
    return mm[file_off : file_off + min(4096, length)]


def main():
    parser = argparse.ArgumentParser(description="Address-based diff of two heap dumps.")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--before-index", required=True)
    parser.add_argument("--after-index", required=True)
    parser.add_argument("--min-delta", type=int, default=-50)
    parser.add_argument("--max-delta", type=int, default=50)
    parser.add_argument("--all", action="store_true", help="report all changed byte positions")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    before_idx = json.loads(Path(args.before_index).read_text(encoding="utf-8"))["entries"]
    after_idx = json.loads(Path(args.after_index).read_text(encoding="utf-8"))["entries"]
    before_map = build_page_map(before_idx)
    after_map = build_page_map(after_idx)

    changes = []
    with open(args.before, "rb") as bf, open(args.after, "rb") as af:
        bm = mmap.mmap(bf.fileno(), 0, access=mmap.ACCESS_READ)
        am = mmap.mmap(af.fileno(), 0, access=mmap.ACCESS_READ)
        for addr, be, ae in iterate_pages(before_map, after_map):
            if be is None or ae is None:
                continue
            b = read_page(bm, be)
            a = read_page(am, ae)
            n = min(len(b), len(a))
            if n <= 0 or b[:n] == a[:n]:
                continue

            if args.all:
                diff_pos = [p for p in range(n) if b[p] != a[p]]
                for p in diff_pos[:30]:
                    s = max(0, p - 8)
                    e = min(n, p + 16)
                    changes.append(
                        {
                            "size": 1,
                            "address": hex(addr + p),
                            "oldHex": b[s:e].hex(),
                            "newHex": a[s:e].hex(),
                        }
                    )
                continue

            # 4-byte and 8-byte aligned small integer deltas
            for p in range(0, n - 3, 4):
                bv = struct.unpack_from("<i", b, p)[0]
                av = struct.unpack_from("<i", a, p)[0]
                delta = av - bv
                if args.min_delta <= delta <= args.max_delta and bv != av:
                    changes.append(
                        {
                            "size": 4,
                            "address": hex(addr + p),
                            "old": bv,
                            "new": av,
                            "delta": delta,
                        }
                    )
            for p in range(0, n - 7, 8):
                bv = struct.unpack_from("<q", b, p)[0]
                av = struct.unpack_from("<q", a, p)[0]
                delta = av - bv
                if args.min_delta <= delta <= args.max_delta and bv != av:
                    changes.append(
                        {
                            "size": 8,
                            "address": hex(addr + p),
                            "old": bv,
                            "new": av,
                            "delta": delta,
                        }
                    )
            if len(changes) >= args.limit:
                break

    if args.out:
        Path(args.out).write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {len(changes)} changes -> {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        for c in changes:
            print(c)


if __name__ == "__main__":
    main()
