"""热更新替换工具：等待旧进程退出后，用新 exe 替换目标并重启。"""

import argparse
import os
import shutil
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="要替换的 exe 路径")
    parser.add_argument("--new", required=True, help="下载好的新 exe 路径")
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    new = os.path.abspath(args.new)
    backup = target + ".old"

    # 给旧程序一点退出时间
    time.sleep(3)

    replaced = False
    for _ in range(30):
        try:
            if os.path.exists(target):
                if os.path.exists(backup):
                    os.remove(backup)
                shutil.copy2(target, backup)
            shutil.copy2(new, target)
            replaced = True
            break
        except (PermissionError, OSError):
            time.sleep(1)

    if not replaced:
        if sys.stderr is not None:
            print("更新替换失败：目标文件被占用或不可写", file=sys.stderr)
        return 1

    try:
        os.remove(new)
    except OSError:
        pass

    subprocess.Popen(
        [target],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
