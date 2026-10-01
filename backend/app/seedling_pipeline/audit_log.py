"""核对日志留档。

每次跑数据准备都把过程与核对结果写到 backend/logs/seedling_prepare/ 下：
- 一份带时间戳的明细日志（永久留档，可追溯每次运行）；
- latest.log 始终指向最近一次，方便直接查看；
- latest.json 是最近一次的结构化结果，接口与 status 都读它。

日志路径是确定的、文件化的，换机器也能在同一相对位置找到，不依赖任何外部服务。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "seedling_prepare"


def _paths() -> tuple[Path, Path, Path]:
    """返回本次使用的日志目录与文件；测试可改写 LOG_DIR 到临时目录。"""
    log_dir = Path(LOG_DIR)
    return log_dir, log_dir / "latest.log", log_dir / "latest.json"


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        "苗木基地数据准备 - 核对日志",
        f"运行时间：{report.get('ran_at')}",
        f"数据版本：{report.get('data_version')}  来源：{report.get('source')}",
        f"数量口径：出圃数量与在圃数量不一致时，以【{report.get('authority')}】为准",
        f"数量指纹：{report.get('checksum')}",
        f"品种数：{report.get('variety_count')}  苗圃数：{report.get('nurseries')}",
        f"出圃合计：{report.get('total_outplanted')}  在圃合计：{report.get('total_in_nursery')}  "
        f"总计：{report.get('total')}",
        f"本次导入：认下新编号 {report.get('inserted')} 个，重复编号跳过 {report.get('skipped')} 个",
        f"核对条目：{report.get('checked')}  结果：{'通过' if report.get('ok') else '不通过'}",
        f"数据是否就绪：{'是' if report.get('ready') else '否（核对未通过，不算准备好）'}",
    ]
    codes = report.get("mismatch_codes") or []
    if codes:
        lines.append("对不上的苗圃编号：" + "、".join(codes))
    issues = report.get("issues") or []
    if issues:
        lines.append("")
        lines.append("问题明细：")
        for item in issues:
            lines.append(
                f"  - [{item.get('苗圃编号')}] {item.get('rule')}：{item.get('message')}"
            )
    else:
        lines.append("问题明细：无")
    lines.append("")
    return "\n".join(lines)


def archive(report: dict[str, Any]) -> dict[str, Any]:
    """把一次运行结果落盘留档，返回各文件路径。"""
    log_dir, latest_log, latest_json = _paths()
    log_dir.mkdir(parents=True, exist_ok=True)
    ran_at = report.get("ran_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    stamp = ran_at.replace(":", "").replace("-", "").replace("T", "-")

    text = _render_text(report)
    stamped = log_dir / f"prepare-{stamp}.log"
    stamped.write_text(text, encoding="utf-8")
    latest_log.write_text(text, encoding="utf-8")
    latest_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "log_dir": str(log_dir),
        "log_file": str(stamped),
        "latest_log": str(latest_log),
    }


def load_latest() -> dict[str, Any] | None:
    """读取最近一次结构化结果；从未跑过时返回 None。"""
    _, _, latest_json = _paths()
    if not latest_json.exists():
        return None
    try:
        return json.loads(latest_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_latest_log() -> str | None:
    _, latest_log, _ = _paths()
    if not latest_log.exists():
        return None
    return latest_log.read_text(encoding="utf-8")
