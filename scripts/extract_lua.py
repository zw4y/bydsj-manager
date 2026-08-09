import argparse
import re
import sys
from pathlib import Path


KEYWORDS = [
    "PropDef",
    "PropId",
    "SKILL_GODLAMP",
    "SKILL_FREE_SHOT_LOCK",
    "SKILL_FREE_SHOT_RAGE",
    "SkillID",
    "宝箱配置",
    "阿拉丁",
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


def main():
    parser = argparse.ArgumentParser(description="Extract readable text lines around Lua config keywords.")
    parser.add_argument("--dump", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    data = Path(args.dump).read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\r\r\n")

    out_lines = []
    for kw in KEYWORDS:
        count = 0
        for i, line in enumerate(lines):
            if kw in line:
                out_lines.append(f"### {kw} @ line {i}")
                for j in range(max(0, i - 1), min(len(lines), i + 3)):
                    out_lines.append(f"  {j}: {lines[j].strip()[:300]}")
                out_lines.append("")
                count += 1
                if count >= 12:
                    break

    result = "\n".join(out_lines)
    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
        print(f"saved -> {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(result)


if __name__ == "__main__":
    main()
