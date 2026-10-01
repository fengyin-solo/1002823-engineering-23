"""苗木基地数据准备流程的命令行入口。

用法：
    .venv/bin/python -m app.seedprep.cli            完整跑一遍
    .venv/bin/python -m app.seedprep.cli --check    只做依赖检查

退出码：0 准备完成（核对通过且导入完成）；1 依赖缺失；2 核对不通过/未准备好。
"""
from __future__ import annotations

import argparse
import json
import sys

from app.seedprep.dependencies import check_dependencies, render_missing
from app.seedprep.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="苗木基地数据准备流水线")
    parser.add_argument("--check", action="store_true", help="只检查依赖，不执行核对与导入")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出准备报告")
    args = parser.parse_args(argv)

    # 第 1 步：依赖检查。缺依赖时停在安装这一步，并说明缺什么、怎么装。
    missing = check_dependencies()
    if missing:
        message = render_missing(missing)
        if args.json:
            print(json.dumps({"stopped": "install", "missing": [item.__dict__ for item in missing]}, ensure_ascii=False, indent=2))
        else:
            print(message, file=sys.stderr)
        return 1

    if args.check:
        print("依赖检查通过：fastapi、uvicorn、pydantic 均已就绪，可以执行数据准备。")
        return 0

    report = run_pipeline()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"核对结论：{'通过，数据已准备好' if report['ready'] else '不通过，数据不算准备好'}")
        for mismatch in report["核对不通过"]:
            print(f"  对不上：{mismatch['苗圃编号']} 的{mismatch['对不上的项']} —— {mismatch['说明']}")
        totals = report["数量汇总"]
        print(
            f"苗圃总数 {report['导入']['准备总数']}；"
            f"培育 {totals['培育数量']}，出圃 {totals['出圃数量']}，在圃 {totals['在圃数量']}"
        )
        print(f"核对日志留档：{report['核对日志目录']}{report.get('日志文件', '')}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
