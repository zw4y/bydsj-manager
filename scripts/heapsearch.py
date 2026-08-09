import argparse
import json
import struct
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Search a heap dump for int32/int64 byte patterns.")
    parser.add_argument("--dump", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--ints", help="comma-separated int32 sequence, e.g. 10301,123")
    parser.add_argument("--int64", help="single int64 value to search")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    data = Path(args.dump).read_bytes()
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))

    patterns = []
    if args.ints:
        seq = [int(x) for x in args.ints.split(",")]
        patterns.append(("int32:" + ",".join(map(str, seq)), b"".join(struct.pack("<I", v) for v in seq)))
    if args.int64:
        v = int(args.int64)
        patterns.append((f"int64:{v}", struct.pack("<Q", v)))

    for label, needle in patterns:
        print(f"##### {label} #####")
        count = 0
        pos = 0
        while count < args.limit:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            # find which range entry this file offset belongs to
            addr = None
            for e in index["entries"]:
                if e["fileOffset"] <= pos < e["fileOffset"] + e["length"]:
                    addr = e["alignedStart"] + (pos - e["fileOffset"])
                    break
            print(f"file offset {hex(pos)} -> address {hex(addr) if addr else '?'}")
            pos += 1
            count += 1
        if count == 0:
            print("no hits")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
