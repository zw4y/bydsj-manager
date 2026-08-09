import argparse
import json
import mmap
import struct
import sys
from pathlib import Path


def scan_changes(before_path, after_path, index_path, min_delta, max_delta):
    before = Path(before_path).read_bytes()
    after = Path(after_path).read_bytes()
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))

    changes = []
    for e in index["entries"]:
        off = e["fileOffset"]
        length = e["length"]
        b = before[off : off + length]
        a = after[off : off + length]
        base = e["alignedStart"]

        # find changed chunks (4KB)
        chunk = 4096
        pos = 0
        while pos < length:
            end = min(pos + chunk, length)
            if b[pos:end] != a[pos:end]:
                # scan 4-byte aligned values within this chunk
                for p in range(pos, end - 3, 4):
                    bv = struct.unpack_from("<i", b, p)[0]
                    av = struct.unpack_from("<i", a, p)[0]
                    delta = av - bv
                    if min_delta <= delta <= max_delta and bv != av:
                        changes.append(
                            {
                                "size": 4,
                                "address": hex(base + p),
                                "old": bv,
                                "new": av,
                                "delta": delta,
                            }
                        )
                for p in range(pos, end - 7, 8):
                    bv = struct.unpack_from("<q", b, p)[0]
                    av = struct.unpack_from("<q", a, p)[0]
                    delta = av - bv
                    if min_delta <= delta <= max_delta and bv != av:
                        changes.append(
                            {
                                "size": 8,
                                "address": hex(base + p),
                                "old": bv,
                                "new": av,
                                "delta": delta,
                            }
                        )
            pos = end
    return changes


def main():
    parser = argparse.ArgumentParser(description="Diff two heap dumps for small integer changes.")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--min-delta", type=int, default=-10)
    parser.add_argument("--max-delta", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    changes = scan_changes(args.before, args.after, args.index, args.min_delta, args.max_delta)
    if args.out:
        Path(args.out).write_text(json.dumps(changes, indent=2), encoding="utf-8")
        print(f"saved {len(changes)} changes -> {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        for c in changes:
            print(c)


if __name__ == "__main__":
    main()
