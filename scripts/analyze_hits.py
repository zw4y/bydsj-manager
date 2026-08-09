import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def decode_ctx(ctx: bytes, encoding: str):
    return ctx.decode("utf-16le" if encoding == "utf16" else "utf-8", errors="replace")


def show(hit):
    ctx = bytes.fromhex(hit["contextHex"])
    if hit["encoding"] == "utf16":
        needle = hit["name"].encode("utf-16le")
    else:
        needle = hit["name"].encode("utf-8")
    pos = ctx.find(needle)
    if pos < 0:
        pos = 256
    start = max(0, pos - 64)
    end = min(len(ctx), pos + len(needle) + 160)
    print(f'[{hit["name"]} {hit["encoding"]}] {hit["address"]} {hit["perms"]} path={hit["path"] or "<heap>"}')
    print(f"  text={decode_ctx(ctx[start:end], hit['encoding'])!r}")
    print(f"  hex={ctx[max(0, pos - 32): pos + len(needle) + 80].hex()}")


def main():
    hits = json.loads((ROOT / "hits.json").read_text(encoding="utf-8"))["hits"]
    rare = {"绿灵石", "紫晶石", "原石精华", "金刚石", "血精石", "战魂自选礼盒"}
    print("=== rare hits ===")
    for h in hits:
        if h["name"] in rare:
            show(h)
            print()

    print("=== 神灯 utf8 hits ===")
    for h in hits:
        if h["name"] == "神灯" and h["encoding"] == "utf8":
            show(h)
            print()

    print("=== 紫晶石 / 原石精华 / 号角 utf16 hits ===")
    for h in hits:
        if h["name"] in ("紫晶石", "原石精华", "号角") and h["encoding"] == "utf16":
            show(h)
            print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
