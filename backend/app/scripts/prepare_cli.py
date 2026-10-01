#!/usr/bin/env python3
"""苗木数据准备命令行入口（可重复执行）。

流程：读取按品种分组的示例数据 -> 幂等导入 -> 自动核对 -> 就绪闸门 -> 日志留档。

退出码：
  0  核对通过、数据已就绪
  2  执行成功但核对未通过（数据不算准备好，已把对不上的编号打印并存日志）
  5  数据文件读取失败等流水线错误

示例：
  python3 -m app.scripts.prepare_cli                 # 用仓库内置示例数据
  python3 -m app.scripts.prepare_cli --file x.json   # 用别的批次数据做核对
"""
from __future__ import annotations

import argparse
import sys

from app.seedling_pipeline.pipeline import prepare_seedlings
from app.store import store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="苗木基地数据准备流水线")
    parser.add_argument("--file", default=None, help="指定示例数据 JSON（默认用内置 seedling_samples.json）")
    args = parser.parse_args(argv)

    result = prepare_seedlings(sample_path=args.file, store=store)
    print(result.message)

    report = result.report
    if report.get("logs"):
        print(f"核对日志：{report['logs'].get('latest_log')}")
    print(f"数量指纹 checksum：{report.get('checksum', '-')}")

    if not result.ok:
        return 5
    if not result.ready:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
