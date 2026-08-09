import argparse
import json
import sys
import time
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parent.parent
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


def find_target(device):
    for proc in device.enumerate_processes():
        name = (proc.name or "").lower()
        if "fishing" in name or "shiyi" in name or "by3d" in name:
            return proc
    return None


def main():
    parser = argparse.ArgumentParser(description="Scan game memory for item name strings.")
    parser.add_argument("--out", default=str(ROOT / "hits.json"))
    parser.add_argument("--names", default="")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    device = frida.get_usb_device(timeout=10)
    if args.names:
        selected = [n.strip() for n in args.names.split(",") if n.strip()]
    else:
        selected = NAMES

    target = None
    for attempt in range(3):
        target = find_target(device)
        if target is not None:
            break
        print(f"Attempt {attempt + 1}: game process not found, retrying...", file=sys.stderr)
        time.sleep(3)
    if target is None:
        print("ERROR: game process not found", file=sys.stderr)
        sys.exit(1)
    print(f"Attaching to {target.name} (pid={target.pid})", file=sys.stderr)

    names_payload = [{"key": f"item{i:02d}", "name": name} for i, name in enumerate(selected)]
    template = (ROOT / "scripts" / "scan_names.js").read_text(encoding="utf-8")
    source = template.replace("__NAMES__", json.dumps(names_payload, ensure_ascii=False))

    session = None
    for attempt in range(3):
        try:
            session = device.attach(target.pid)
            break
        except frida.ProcessNotFoundError:
            print(f"Attach attempt {attempt + 1}: process gone, re-enumerating...", file=sys.stderr)
            target = find_target(device)
            time.sleep(3)
    if session is None:
        print("ERROR: failed to attach to game process", file=sys.stderr)
        sys.exit(1)
    script = session.create_script(source)
    hits = []
    state = {"done": False}

    def on_message(message, data):
        if message["type"] == "send":
            payload = message["payload"]
            if payload["type"] == "progress":
                print(
                    f"progress: {payload['scannedRanges']} ranges, {payload['hitCount']} hits, "
                    f"{payload['elapsedMs']}ms",
                    file=sys.stderr,
                )
            elif payload["type"] == "done":
                hits.extend(payload["hits"])
                print(
                    f"done: {payload['scannedRanges']} ranges, {payload['totalBytes']} bytes, "
                    f"{len(payload['hits'])} hits, {payload['elapsedMs']}ms",
                    file=sys.stderr,
                )
                result = {
                    "attached": {"name": target.name, "pid": target.pid},
                    "ranges": payload["scannedRanges"],
                    "totalBytes": payload["totalBytes"],
                    "elapsedMs": payload["elapsedMs"],
                    "hits": hits,
                }
                state["done"] = True
                Path(args.out).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"Saved {len(hits)} hits to {args.out}")
        elif message["type"] == "error":
            print(f"SCRIPT ERROR: {message.get('stack') or message.get('description')}", file=sys.stderr)

    script.on("message", on_message)
    script.load()

    deadline = time.time() + args.timeout
    while time.time() < deadline and not state["done"]:
        time.sleep(1)

    try:
        session.detach()
    except Exception:
        pass


if __name__ == "__main__":
    main()
