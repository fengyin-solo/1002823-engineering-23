"""数据准备流水线编排：把依赖检查之外的各步按固定顺序跑一遍。

固定步骤：读取品种目录与按品种分文件的示例数据 → 去重 + 自洽核对 →
（仅核对通过）按苗圃编号首次导入 → 写 prepared.json / report.json → 留档核对日志。

核对不通过时只写核对报告与日志，不动 prepared.json、不执行导入：
没核过的数据不算准备好。重复导入同一批编号时已存在的编号原样保留（只认第一次），
新编号追加在后面，因此同一套流程重复跑结果与签名完全一致。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.seedprep.catalog import load_catalog, load_samples
from app.seedprep.paths import LOG_DIR, PREPARED_FILE, REPORT_FILE, SAMPLES_DIR
from app.seedprep.policy import CYCLE_RULE_TEXT, QUANTITY_RULE_SOURCE, QUANTITY_RULE_TEXT
from app.seedprep.repository import canonical_payload, load_prepared, save_prepared
from app.seedprep.validation import normalize_row, reconcile


def _sums(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "培育数量": sum(int(row.get("培育数量", 0)) for row in entries),
        "出圃数量": sum(int(row.get("出圃数量", 0)) for row in entries),
        "在圃数量": sum(int(row.get("在圃数量", 0)) for row in entries),
    }


def _variety_groups(entries: list[dict[str, Any]]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for row in entries:
        variety = str(row.get("培育品种", ""))
        groups[variety] = groups.get(variety, 0) + 1
    return {variety: groups[variety] for variety in sorted(groups)}


def _write_log(lines: list[str], log_dir: Path | None = None) -> Path:
    """把本次核对日志按时间戳留档，并同步一份 latest.log 方便直接查看。"""
    directory = log_dir or LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = directory / f"prepare-{stamp}.log"
    content = "\n".join(lines) + "\n"
    log_path.write_text(content, encoding="utf-8")
    (directory / "latest.log").write_text(content, encoding="utf-8")
    return log_path


def _persist_report(report: dict[str, Any], report_path: Path | None = None) -> None:
    """写确定性核对报告：无时间戳，同一份输入在任何环境得到同一份内容。"""
    target = report_path or REPORT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_pipeline(
    *,
    samples_dir: Path | None = None,
    prepared_path: Path | None = None,
    report_path: Path | None = None,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """执行一遍数据准备流程，返回纯字典报告（同时落 report.json，核对失败也写）。"""
    directory = samples_dir or SAMPLES_DIR
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines = [
        f"[{started}] 苗木基地数据准备流程开始",
        f"数量口径：{QUANTITY_RULE_TEXT}",
        f"周期口径：{CYCLE_RULE_TEXT}",
    ]

    catalog = load_catalog()
    log_lines.append(f"品种目录载入 {len(catalog)} 个品种：{'、'.join(sorted(catalog)) or '空'}")

    sample_rows, load_errors = load_samples(directory)
    sample_files = sorted(path.name for path in directory.glob("*.json"))
    log_lines.append(
        f"示例数据按培育品种分文件，共读取 {len(sample_files)} 个文件："
        f"{'、'.join(sample_files) or '无'}，{len(sample_rows)} 条记录"
    )

    result = reconcile(sample_rows, catalog, load_errors=load_errors)
    for item in result.skipped_duplicates:
        log_lines.append(f"去重：苗圃编号 {item['苗圃编号']} {item['说明']}，已跳过")
    for mismatch in result.mismatches:
        log_lines.append(f"核对不通过：{mismatch.code} 的{mismatch.kind} —— {mismatch.detail}")

    existing = load_prepared(prepared_path)
    report: dict[str, Any] = {
        "ready": False,
        "数量口径": QUANTITY_RULE_SOURCE,
        "数量规则": QUANTITY_RULE_TEXT,
        "周期规则": CYCLE_RULE_TEXT,
        "示例文件": sample_files,
        "示例记录数": len(sample_rows),
        "去重跳过": result.skipped_duplicates,
        "核对不通过": [mismatch.as_dict() for mismatch in result.mismatches],
        "导入": {"已存在编号": [], "本次新增编号": [], "准备总数": len(existing)},
        "品种分组": _variety_groups(existing),
        "数量汇总": _sums(existing),
        "signature": hashlib.sha256(canonical_payload(existing)).hexdigest(),
        "核对日志目录": "var/logs/seedling/",
        "准备数据文件": "data/seedling/prepared.json",
    }

    if not result.passed:
        log_lines.append(
            f"核对结论：不通过，{len(result.mismatches)} 项对不上，"
            "不执行导入，prepared.json 保持上一版，本次不算准备好"
        )
        report["日志文件"] = _write_log(log_lines, log_dir).name
        _persist_report(report, report_path)
        return report

    known_codes = {str(row.get("苗圃编号", "")) for row in existing}
    next_id = max((int(row.get("id", 0)) for row in existing), default=0) + 1
    already_known: list[str] = []
    newly_imported: list[str] = []

    # 去重已保证同批编号只出现一次；跨批次重复导入只认第一次，不叠成两份
    for row in result.valid_rows:
        code = str(row["苗圃编号"]).strip()
        if code in known_codes:
            already_known.append(code)
            log_lines.append(f"导入：苗圃编号 {code} 已存在，只认第一次的数据，本次跳过不叠加")
            continue
        existing.append(normalize_row(row, catalog, next_id))
        next_id += 1
        known_codes.add(code)
        newly_imported.append(code)
        log_lines.append(f"导入：苗圃编号 {code}（{row.get('培育品种', '')}）首次导入")

    entries = sorted(existing, key=lambda row: int(row.get("id", 0)))
    signature = hashlib.sha256(canonical_payload(entries)).hexdigest()
    save_prepared(entries, signature, quantity_rule_source=QUANTITY_RULE_SOURCE, path=prepared_path)

    totals = _sums(entries)
    log_lines.append(
        f"导入完成：新增 {len(newly_imported)} 条，已有跳过 {len(already_known)} 条，"
        f"准备总数 {len(entries)}；培育 {totals['培育数量']}，出圃 {totals['出圃数量']}，"
        f"在圃 {totals['在圃数量']}"
    )
    log_lines.append(f"核对结论：通过，数据签名 {signature}")

    report.update({
        "ready": True,
        "导入": {
            "已存在编号": sorted(already_known),
            "本次新增编号": newly_imported,
            "准备总数": len(entries),
        },
        "品种分组": _variety_groups(entries),
        "数量汇总": totals,
        "signature": signature,
        "日志文件": _write_log(log_lines, log_dir).name,
    })
    _persist_report(report, report_path)
    return report


def load_status(report_path: Path | None = None, prepared_path: Path | None = None) -> dict[str, Any]:
    """读取最近一次准备结果，供状态接口与页面展示；从没跑过则明确提示未准备。"""
    target = report_path or REPORT_FILE
    if not target.exists():
        return {
            "ready": False,
            "message": "尚未执行过数据准备，请先运行 ./prepare.sh 或在页面上发起准备",
            "数量口径": QUANTITY_RULE_SOURCE,
            "数量规则": QUANTITY_RULE_TEXT,
        }
    report = json.loads(target.read_text(encoding="utf-8"))
    if report.get("ready") and not (prepared_path or PREPARED_FILE).exists():
        report["ready"] = False
        report["message"] = "核对报告为通过，但 prepared.json 缺失，数据不算准备好，请重新执行准备"
    return report
