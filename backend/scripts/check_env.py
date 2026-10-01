#!/usr/bin/env python3
"""依赖自检（只用标准库，本身不依赖第三方包）。

在真正安装/启动之前先跑它：逐个 import requirements.txt 里声明的依赖，
缺什么就把【缺哪个包、怎么装】明确打印出来，并以非零码退出，让流程停在安装这一步，
而不是带着残缺环境继续往下跑、最后在一个看不懂的报错里失败。

退出码：
  0  依赖齐全
  3  缺少依赖（已打印缺失清单与安装命令）
  4  Python 版本过低
"""
from __future__ import annotations

import importlib.util
import re
import sys

MIN_PYTHON = (3, 10)

# requirements.txt 里的发行名 -> 实际 import 的模块名（不一致时才需要登记）。
DIST_TO_MODULE = {
    "uvicorn": "uvicorn",
}


def parse_requirements(path: str) -> list[tuple[str, str]]:
    """从 requirements.txt 提取 (发行名, import模块名)，忽略注释/空行/extras 标记。"""
    pairs: list[tuple[str, str]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"[依赖自检] 读不到 requirements.txt：{exc}", file=sys.stderr)
        sys.exit(3)

    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        # 取包名主体，丢掉版本与 extras：uvicorn[standard]>=0.29 -> uvicorn
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip()
        if not name:
            continue
        module = DIST_TO_MODULE.get(name.lower(), name)
        pairs.append((name, module))
    return pairs


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        cur = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        need = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"
        print(
            f"[依赖自检] Python 版本过低：当前 {cur}，需要 {need}。\n"
            f"           请先安装 {need} 再重试，流程停在环境准备这一步。",
            file=sys.stderr,
        )
        return 4

    import os
    req = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "requirements.txt")
    pairs = parse_requirements(req)

    missing: list[str] = []
    for dist, module in pairs:
        if importlib.util.find_spec(module) is None:
            missing.append(dist)

    if missing:
        print("[依赖自检] 依赖未装齐，流程停在安装这一步，暂不继续导入/启动。", file=sys.stderr)
        print("缺少以下依赖：", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        print("", file=sys.stderr)
        print("请先安装依赖，任选一种：", file=sys.stderr)
        print("  make install-setup     # 用脚本自动装（含引导 pip）", file=sys.stderr)
        print("  ./scripts/bootstrap.sh # 仅后端：自检 -> 安装 -> 复验", file=sys.stderr)
        print("  python3 -m pip install -r backend/requirements.txt", file=sys.stderr)
        return 3

    print(f"[依赖自检] 通过：{len(pairs)} 个依赖均已就绪（Python "
          f"{sys.version_info.major}.{sys.version_info.minor}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
