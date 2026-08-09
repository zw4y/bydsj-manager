import argparse
import re
import sys
from pathlib import Path


def clean(chunk: bytes) -> str:
    text = chunk.decode("utf-8", errors="replace")
    text = text.replace("\r\r\n", " | ")
    text = text.replace("\r\n", " | ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", required=True)
    parser.add_argument("--kw", action="append", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--before", type=int, default=300)
    parser.add_argument("--after", type=int, default=400)
    args = parser.parse_args()

    data = Path(args.dump).read_bytes()
    for kw in args.kw:
        needle = kw.encode("utf-8")
        print(f"##### {kw} #####")
        count = 0
        pos = 0
        while count < args.limit:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            start = max(0, pos - args.before)
            end = min(len(data), pos + args.after)
            print(f"@{hex(pos)}: ...{clean(data[start:end])}...")
            print()
            pos += len(needle)
            count += 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
